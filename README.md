# Frame Cut Audit

**Find the cuts your export actually made.**

A video can export successfully and still start half a second before the mark you set. Frame Cut Audit compares your original video, exported video, and cut list. It shows where each exported range came from, how far either boundary moved, and where to replay that cut.

In a test splice, the first excerpt was meant to start at 4.500 seconds. It started at 4.000 seconds. The second excerpt matched the plan.

| Excerpt | Planned range in source | Detected range in source | Result |
| --- | --- | --- | --- |
| First | 4.500–6.000 s | 4.000–6.000 s | Starts 500 ms early (4 frames) |
| Second | 0.000–2.000 s | 0.000–2.000 s | Matches |

The HTML report opens locally and links to both ends of each excerpt. A separate JSON report gives scripts the exact frame indices and time differences.

[Test report in English and Chinese](REPORT.md) · [Workflow diagram (PNG)](frame-cut-audit-flow.png)

## Use as an Agent Skill

Place the `frame-cut-audit` folder in a skill directory supported by your agent. The folder includes `SKILL.md` and the scripts. Give the agent the source video, the export, and the intended cut times or cut list. For example, “Check whether `export.mp4` kept seconds 4.5–6.5 from `source.mp4`, and give me a replay link for any difference.”

## Run from a terminal

Install Python 3.9 or later and FFmpeg 7 or later. Add `ffmpeg` to `PATH`. The audit uses the Python standard library.

List the **kept** source intervals in export order. Times are seconds, starts are inclusive, and ends are exclusive. The label and header are optional. A blank start means zero. A blank end denotes a marker, which the audit skips. Adjacent ranges with no gap in their source frames appear as one range.

```csv
start,end,label
4.5,6.5,Opening excerpt
0,2,Closing excerpt
```

```sh
python3 scripts/cut_audit.py source.mp4 export.mp4 cuts.csv --output audit-run
```

Open `audit-run/audit.html` in a browser with support for the source and export formats. A replay link opens the export near the measured boundary. Keep the files in their original locations for the report links to work. The tool also writes `audit-run/audit.json` with the requested times, observed source and export ranges, and per-edge differences.

| Exit code | Result |
| --- | --- |
| `0` | The measured ranges match the planned frames. |
| `1` | A boundary or the number of continuous ranges differs. |
| `2` | An input or execution error prevented the audit. |
| `3` | The frame evidence needs manual review. |

For cuts between frames, the report checks the first source frame at or after each requested boundary. Differences are relative to those frame boundaries. A negative difference means the export boundary occurred earlier in the source. JSON frame indices are zero-based and ends are exclusive.

## Scope and method

This version checks one source and one export. It compares the first real video track on each. FFmpeg decodes the frames and calculates a SHA-256 fingerprint for each one. Frame fingerprints unique in the source locate candidate ranges. The script verifies every frame in those ranges and checks where consecutive ranges join.

Use same-resolution exports that preserve the decoded frame pixels, such as stream copies. Re-encoding that changes pixels, effects, scaling, and repeated footage can require manual review. The audit measures cut boundaries in video frames. Audio sync and other delivery checks are separate.

## Verify or maintain

```sh
python3 tests/e2e.py
```

The test script generates temporary videos with FFmpeg and removes them on exit. It uses FFmpeg with `libx264` to create fixtures. It verifies an exact cut, a half-second early start, an early end, reordered cuts, a missing range, adjacent ranges, ambiguous frames, and invalid input. It also checks the replay link for the second range.

Version 0.1.0. MIT license.
