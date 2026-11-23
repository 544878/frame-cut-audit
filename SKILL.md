---
name: frame-cut-audit
description: Check whether a video export kept the planned source ranges. Use when a user supplies a source video, an exported cut or splice, and a cut list or intended timestamps, and wants to find early cuts, late cuts, or missing ranges.
---

# Frame Cut Audit

1. Identify the local source, local export, and the kept ranges in export order. If the user gave timestamps, write them to a CSV with `start,end,label` columns, in seconds. Each range keeps its start and excludes its end. Get missing cut times from the user or their plan before measuring the export.
2. With Python 3.9+ and FFmpeg 7+ on `PATH`, run this command with the script path resolved from this skill folder. Choose a fresh report directory.

   ```sh
   python3 scripts/cut_audit.py source.mp4 export.mp4 cuts.csv --output audit-run
   ```

3. Read `audit.json` and give the user the status and `audit.html`. Report each measured start or end difference in seconds and frames. Negative means earlier in the source. Link the HTML report for replay.
4. Use these exit codes. `0` means the measured ranges match. `1` means measured ranges differ. `3` means exact matching could not place the frames uniquely, so ask for manual review. `2` means an input or execution error. Use the error message to correct the input or report the blocker.

This check measures video frame ranges in a single source. Same-resolution stream-copy exports preserve the frame pixels the tool compares. If the requested export has changed pixels or ambiguous joins, keep that export and report that it needs manual review. Keep source and export files in place so the replay links resolve.
