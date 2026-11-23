import os
from html import escape
from pathlib import Path
from urllib.parse import quote


def media_link(path: Path, report_directory: Path, time: float, label: str) -> str:
    try:
        url = quote(Path(os.path.relpath(path, report_directory)).as_posix())
    except ValueError:
        url = path.as_uri()
    href = escape(f"{url}#t={time:.9f}", quote=True)
    return f'<a href="{href}">{escape(label)}</a>'


def span(item: dict) -> str:
    return f"{item['start']:.3f}–{item['end']:.3f} s"


def delta(segment: dict, edge: str) -> str:
    frames = segment[f"{edge}_delta_frames"]
    milliseconds = segment[f"{edge}_delta_seconds"] * 1000
    return f"{frames:+d} frames ({milliseconds:+.1f} ms)" if frames else "0 frames"


def table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    heading = "".join(f'<th scope="col">{title}</th>' for title in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table"><table><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table></div>'


def render_report(result: dict, source: Path, export: Path, directory: Path) -> str:
    status = {"match": "Matches plan", "different": "Cut differences found", "review": "Manual review needed"}[result["status"]]
    rows = []
    for expected, observed, segment in zip(result["expected"], result["observed"], result["segments"]):
        original = observed["source"]
        actual = observed["export"]
        start_link = media_link(export, directory, actual["start"], f"Start at {actual['start']:.3f} s")
        near_end = max(actual["start"], actual["end"] - 0.5)
        end_link = media_link(export, directory, near_end, f"Near end at {near_end:.3f} s")
        rows.append((
            escape(expected["label"]), span(expected), span(original), delta(segment, "start"), delta(segment, "end"),
            f"{start_link}<br>{end_link}",
        ))
    if rows:
        content = table(("Range", "Planned in source", "Found in source", "Start change", "End change", "Replay"), rows)
    else:
        expected_rows = [(escape(item["label"]), span(item)) for item in result["expected"]]
        content = '<h2>Planned ranges</h2>' + table(("Range", "Planned in source"), expected_rows)
        observed_rows = [
            (span(item["source"]), media_link(export, directory, item["export"]["start"], span(item["export"])))
            for item in result["observed"]
        ]
        if observed_rows:
            content += '<h2>Detected ranges</h2>' + table(("Found in source", "Replay in export"), observed_rows)

    source_link = media_link(source, directory, 0, source.name)
    export_link = media_link(export, directory, 0, export.name)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Frame Cut Audit</title>
<style>
  :root {{ color-scheme: light dark; font: 16px/1.5 system-ui, sans-serif; }}
  body {{ margin: 0 auto; max-width: 74rem; padding: 2rem 1rem; }}
  h1, h2 {{ line-height: 1.2; }}
  h1 {{ margin: 0; }}
  .status {{ font-size: 1.25rem; font-weight: 650; margin-bottom: 0; }}
  .table {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
  th, td {{ border-bottom: 1px solid GrayText; padding: .6rem .75rem; text-align: left; }}
  th {{ white-space: nowrap; }}
  td:first-child {{ overflow-wrap: anywhere; }}
</style>
</head>
<body>
<main>
<h1>Frame Cut Audit</h1>
<p class="status">{status}</p>
<p>{escape(result['detail'])}</p>
<p>Source {source_link} · Export {export_link} · <a href="audit.json">JSON report</a></p>
{content}
</main>
</body>
</html>
"""
