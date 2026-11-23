from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from bisect import bisect_left
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from render_report import render_report


class AuditError(Exception):
    pass


class UnresolvedCut(Exception):
    pass


@dataclass(frozen=True)
class Cut:
    start: Fraction
    end: Fraction
    label: str


@dataclass(frozen=True)
class Timeline:
    hashes: list[str]
    boundaries: list[Fraction]
    dimensions: str


@dataclass(frozen=True)
class Range:
    start: int
    stop: int


@dataclass(frozen=True)
class PlannedRange:
    cut: Cut
    frames: Range


def inspect_frames(video: Path) -> Timeline:
    command = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-xerror",
        "-copyts", "-start_at_zero", "-protocol_whitelist", "file", "-noautorotate",
        "-i", str(video), "-map", "0:V:0", "-c:v", "rawvideo", "-threads:v", "1",
        "-fps_mode", "passthrough", "-enc_time_base", "demux", "-avoid_negative_ts", "disabled",
        "-f", "framehash", "-hash", "sha256", "-",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError as exc:
        raise AuditError("Install FFmpeg 7 or later and put it on PATH.") from exc
    if result.returncode:
        raise AuditError(f"Cannot decode {video.name}: {result.stderr.strip()}")

    hashes = []
    timestamps = []
    dimensions = ""
    time_base = None
    last_duration = 0
    try:
        for line in result.stdout.splitlines():
            if line.startswith("#tb 0:"):
                time_base = Fraction(line.split(":", 1)[1].strip())
            elif line.startswith("#dimensions 0:"):
                dimensions = line.split(":", 1)[1].strip()
            elif line and not line.startswith("#"):
                _, _, pts, duration, _, digest = line.split(",")
                timestamps.append(int(pts))
                hashes.append(digest.strip())
                last_duration = int(duration)
    except (ValueError, ZeroDivisionError) as exc:
        raise AuditError(f"Cannot read frame times for {video.name}.") from exc
    if not hashes or not dimensions or not time_base or last_duration <= 0:
        raise AuditError(f"{video.name} has no video frames with measurable bounds.")
    if timestamps[0] < 0 or any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        raise AuditError(f"{video.name} has unsupported frame timestamps.")
    timestamps.append(timestamps[-1] + last_duration)
    return Timeline(hashes, [time_base * tick for tick in timestamps], dimensions)


def read_cuts(path: Path) -> list[Cut]:
    cuts = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file, strict=True)
        saw_row = False
        for row in reader:
            fields = [item.strip() for item in row]
            if not any(fields):
                continue
            if not saw_row and [item.lower() for item in fields] in (["start", "end"], ["start", "end", "label"]):
                saw_row = True
                continue
            saw_row = True
            location = f"CSV line {reader.line_num}"
            if len(fields) not in (2, 3):
                raise AuditError(f"{location} needs start, end and an optional label.")
            start_text, end_text = fields[:2]
            try:
                start = Fraction(start_text or "0")
                end = Fraction(end_text) if end_text else None
            except (ValueError, ZeroDivisionError) as exc:
                raise AuditError(f"{location} needs times in seconds.") from exc
            if start < 0 or (end is not None and end <= start):
                raise AuditError(f"{location} needs 0 <= start < end.")
            if end is not None:
                label = fields[2] if len(fields) == 3 and fields[2] else f"Cut {len(cuts) + 1}"
                cuts.append(Cut(start, end, label))
    if not cuts:
        raise AuditError("The CSV has no cut ranges.")
    return cuts


def snap_plan(cuts: list[Cut], source: Timeline) -> list[PlannedRange]:
    plan = []
    for cut in cuts:
        if cut.end > source.boundaries[-1]:
            raise AuditError(f"{cut.label!r} ends after the source video.")
        start = bisect_left(source.boundaries, cut.start)
        stop = bisect_left(source.boundaries, cut.end)
        if start == stop:
            raise AuditError(f"{cut.label!r} contains no source video frames.")
        if plan and plan[-1].frames.stop == start:
            previous = plan.pop()
            cut = Cut(previous.cut.start, cut.end, f"{previous.cut.label} + {cut.label}")
            start = previous.frames.start
        plan.append(PlannedRange(cut, Range(start, stop)))
    return plan


def anchor_groups(source: list[str], export: list[str]) -> list[tuple[int, int, int]]:
    positions: dict[str, int | None] = {}
    for index, digest in enumerate(source):
        positions[digest] = index if digest not in positions else None

    groups = []
    for index, digest in enumerate(export):
        source_index = positions.get(digest)
        if source_index is None:
            continue
        offset = source_index - index
        if groups and groups[-1][0] == offset:
            _, first, _ = groups[-1]
            groups[-1] = (offset, first, index)
        else:
            groups.append((offset, index, index))
    return groups


def locate_ranges(source: Timeline, export: Timeline) -> list[tuple[Range, Range]]:
    if source.dimensions != export.dimensions:
        raise UnresolvedCut("The source and export have different frame sizes.")
    groups = anchor_groups(source.hashes, export.hashes)
    if not groups:
        raise UnresolvedCut("No exported frame matches a unique source frame.")

    def matches(index: int, offset: int) -> bool:
        position = index + offset
        return 0 <= position < len(source.hashes) and source.hashes[position] == export.hashes[index]

    boundaries = [0]
    for (left, _, last), (right, first, _) in zip(groups, groups[1:]):
        latest = last + 1
        while latest < first and matches(latest, left):
            latest += 1
        earliest = first
        while earliest > last + 1 and matches(earliest - 1, right):
            earliest -= 1
        if earliest != latest:
            detail = "Repeated frames allow more than one join" if earliest < latest else "Frames do not match across the join"
            raise UnresolvedCut(f"{detail} near export frame {first + 1}.")
        boundaries.append(earliest)
    boundaries.append(len(export.hashes))

    ranges = []
    for (offset, _, _), start, stop in zip(groups, boundaries, boundaries[1:]):
        for index in range(start, stop):
            if not matches(index, offset):
                raise UnresolvedCut(f"Export frame {index + 1} does not match its inferred source range.")
        ranges.append((Range(start + offset, stop + offset), Range(start, stop)))
    return ranges


def seconds(time: Fraction) -> float:
    return round(float(time), 9)


def describe_range(frames: Range, video: Timeline) -> dict:
    return {
        "first_frame": frames.start,
        "end_frame_exclusive": frames.stop,
        "start": seconds(video.boundaries[frames.start]),
        "end": seconds(video.boundaries[frames.stop]),
    }


def audit(plan: list[PlannedRange], source: Timeline, export: Timeline) -> dict:
    expected = [
        {"label": item.cut.label, "requested_start": seconds(item.cut.start), "requested_end": seconds(item.cut.end),
         **describe_range(item.frames, source)}
        for item in plan
    ]
    try:
        ranges = locate_ranges(source, export)
    except UnresolvedCut as exc:
        return {"status": "review", "detail": str(exc), "expected": expected, "observed": [], "segments": []}

    observed = [
        {"source": describe_range(original, source), "export": describe_range(output, export)}
        for original, output in ranges
    ]
    if len(ranges) != len(plan):
        detail = f"Expected {len(plan)} continuous ranges. Found {len(ranges)} in the export."
        return {"status": "different", "detail": detail, "expected": expected, "observed": observed, "segments": []}

    segments = []
    for item, (actual, _) in zip(plan, ranges):
        planned = item.frames
        segments.append({
            "start_delta_frames": actual.start - planned.start,
            "end_delta_frames": actual.stop - planned.stop,
            "start_delta_seconds": seconds(source.boundaries[actual.start] - source.boundaries[planned.start]),
            "end_delta_seconds": seconds(source.boundaries[actual.stop] - source.boundaries[planned.stop]),
        })
    different = sum(original != item.frames for item, (original, _) in zip(plan, ranges))
    detail = f"{len(plan) - different} of {len(plan)} ranges match the plan."
    return {"status": "different" if different else "match", "detail": detail,
            "expected": expected, "observed": observed, "segments": segments}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare planned cut ranges with the frames in an exported video.")
    parser.add_argument("source", type=Path, help="original video")
    parser.add_argument("export", type=Path, help="video exported from that source")
    parser.add_argument("cuts", type=Path, help="CSV of kept source ranges in export order")
    parser.add_argument("--output", type=Path, required=True, help="new directory for the JSON and HTML reports")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    args = parser.parse_args()
    try:
        source_path, export_path, cuts_path = (path.resolve() for path in (args.source, args.export, args.cuts))
        for path in (source_path, export_path, cuts_path):
            if not path.is_file():
                raise AuditError(f"Input is not a local file: {path.name}")
        output = args.output.resolve()
        if output.exists():
            raise AuditError("Choose a new output directory.")

        cuts = read_cuts(cuts_path)
        source = inspect_frames(source_path)
        plan = snap_plan(cuts, source)
        export = inspect_frames(export_path)
        result = audit(plan, source, export)
        result.update(schema_version=1, source=source_path.name, export=export_path.name)
        html = render_report(result, source_path, export_path, output)
        output.mkdir(parents=True)
        (output / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "audit.html").write_text(html, encoding="utf-8")
    except (AuditError, OSError, csv.Error, ValueError) as exc:
        print(f"Audit error: {exc}", file=sys.stderr)
        return 2

    print(f"{result['status']}: {result['detail']} Reports: {output}")
    return {"match": 0, "different": 1, "review": 3}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
