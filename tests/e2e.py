from html.parser import HTMLParser
import json
from pathlib import Path
from subprocess import run
import sys
from tempfile import TemporaryDirectory


TOOL = Path(__file__).resolve().parents[1] / "scripts" / "cut_audit.py"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attributes):
        if tag == "a":
            self.urls.append(dict(attributes)["href"])


def ffmpeg(folder, *options):
    return run(["ffmpeg", "-v", "error", "-nostdin", *options], cwd=folder, check=True, capture_output=True, text=True)


def make_video(folder, filter_expression, output):
    ffmpeg(folder, "-f", "lavfi", "-i", filter_expression, "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-g", "16", "-keyint_min", "16", "-sc_threshold", "0", "-bf", "0", output)


def trim(folder, source, start, length, export, *muxer_options):
    ffmpeg(folder, "-ss", start, "-i", source, "-t", length, "-map", "0:v:0", "-c", "copy", *muxer_options, export)


def check(folder, name, source, export, csv_text, expected_exit):
    cuts = f"{name}.csv"
    output = folder / name
    (folder / cuts).write_text(csv_text, encoding="utf-8")
    command = [sys.executable, str(TOOL), source, export, cuts, "--output", name]
    result = run(command, cwd=folder, capture_output=True, text=True)
    assert result.returncode == expected_exit, (command, result.returncode, result.stdout, result.stderr)
    if expected_exit == 2:
        assert not output.exists()
        return {}
    payload = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    html = (output / "audit.html").read_text(encoding="utf-8")
    assert "<script>" not in html
    links = Links()
    links.feed(html)
    return payload, links.urls


def main():
    with TemporaryDirectory(prefix="frame-cut-audit-") as tmp:
        folder = Path(tmp)
        make_video(folder, "testsrc2=size=160x90:rate=8:duration=8", "source.mp4")
        trim(folder, "source.mp4", "4.5", "2", "exact.mp4")
        trim(folder, "source.mp4", "4.5", "2", "early.mp4", "-avoid_negative_ts", "make_zero")

        plan = 'start,end,label\n4.5,6.5,"<script>"\n'
        exact, _ = check(folder, "exact", "source.mp4", "exact.mp4", plan, 0)
        assert exact["observed"][0]["source"]["start"] == 4.5
        assert exact["segments"][0]["start_delta_frames"] == exact["segments"][0]["end_delta_frames"] == 0

        early, _ = check(folder, "early", "source.mp4", "early.mp4", plan, 1)
        assert early["observed"][0]["source"]["start"] == 4.0
        assert early["segments"][0]["start_delta_frames"] == -4
        assert early["segments"][0]["start_delta_seconds"] == -0.5
        assert early["segments"][0]["end_delta_seconds"] == 0

        trim(folder, "source.mp4", "4", "2", "later.mp4")
        trim(folder, "source.mp4", "0", "2", "earlier.mp4")
        (folder / "join.txt").write_text("file 'later.mp4'\nfile 'earlier.mp4'\n", encoding="utf-8")
        ffmpeg(folder, "-f", "concat", "-i", "join.txt", "-c", "copy", "joined # output.mp4")
        reordered, links = check(folder, "reordered", "source.mp4", "joined # output.mp4",
                                 "4,6,Later shot\n,2,Earlier shot\n3,,Marker\n", 0)
        assert [item["source"]["start"] for item in reordered["observed"]] == [4, 0]
        assert [item["export"]["start"] for item in reordered["observed"]] == [0, 2]
        assert "../joined%20%23%20output.mp4#t=2.000000000" in links
        assert "../joined%20%23%20output.mp4#t=3.500000000" in links

        missing, _ = check(folder, "missing", "source.mp4", "later.mp4", "4,6\n0,2\n", 1)
        assert len(missing["expected"]) == 2 and len(missing["observed"]) == 1
        assert not missing["segments"]

        adjacent, _ = check(folder, "adjacent", "source.mp4", "later.mp4", "4,5\n5,6\n", 0)
        assert len(adjacent["expected"]) == len(adjacent["observed"]) == 1

        trim(folder, "source.mp4", "4", "1", "short.mp4")
        short, _ = check(folder, "short", "source.mp4", "short.mp4", "4,6\n", 1)
        assert short["segments"][0]["end_delta_seconds"] == -1

        make_video(folder, "color=black:size=160x90:rate=8:duration=4", "static.mp4")
        trim(folder, "static.mp4", "0", "1", "static-cut.mp4")
        repeated, _ = check(folder, "repeated", "static.mp4", "static-cut.mp4", "0,1\n", 3)
        assert repeated["status"] == "review" and not repeated["observed"]
        check(folder, "bad-csv", "source.mp4", "exact.mp4", "3,2\n", 2)

    print("PASS: exact cut, early start, reordered join with replay links, missing range, adjacent ranges, early end, ambiguous content, invalid CSV")


if __name__ == "__main__":
    main()
