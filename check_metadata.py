import subprocess
import sys
import json
from pathlib import Path

VIDEO = sys.argv[1] if len(sys.argv) > 1 else None
if not VIDEO or not Path(VIDEO).exists():
    print("Usage: python check_metadata.py <video.avi>")
    sys.exit(1)

def run_ffprobe(args):
    return subprocess.run(
        ["ffprobe", "-v", "quiet"] + args + [VIDEO],
        capture_output=True, text=True
    ).stdout.strip()

print(f"File: {VIDEO}\n")

print("=== Stream-level tags ===")
stream_json = run_ffprobe(["-show_entries", "stream_tags", "-of", "json"])
try:
    data = json.loads(stream_json)
    for stream in data.get("streams", []):
        tags = stream.get("tags", {})
        for k, v in tags.items():
            print(f"  {k}: {v}")
    if not data.get("streams"):
        print("  (no stream tags)")
except Exception:
    print(stream_json)

print("\n=== First 10 frames: timecode ===")
tc_out = run_ffprobe([
    "-select_streams", "v:0",
    "-show_entries", "frame_tags=timecode",
    "-read_intervals", "%+#10",
    "-of", "csv=p=0"
])
if tc_out:
    tcs = [l.strip() for l in tc_out.splitlines() if l.strip()]
    print(f"Found {len(tcs)} timecode entries:")
    for t in tcs:
        print(f"  {t}")
else:
    print("  *** TIMECODE NOT FOUND ***")

print("\n=== First 10 frames: recording date/time ===")
dt_out = run_ffprobe([
    "-select_streams", "v:0",
    "-show_entries", "frame_tags=rec_date,rec_time,date,time,creation_time",
    "-read_intervals", "%+#10",
    "-of", "csv=p=0"
])
if dt_out:
    lines = [l.strip() for l in dt_out.splitlines() if l.strip()]
    print(f"Found {len(lines)} entries:")
    for l in lines:
        print(f"  {l}")
else:
    print("  *** RECORDING DATE/TIME NOT FOUND ***")

print("\n=== All available frame tag keys (first 5 frames) ===")
all_tags = run_ffprobe([
    "-select_streams", "v:0",
    "-show_entries", "frame_tags",
    "-read_intervals", "%+#5",
    "-of", "json"
])
try:
    data = json.loads(all_tags)
    seen_keys = set()
    for frame in data.get("frames", []):
        for k in frame.get("tags", {}).keys():
            seen_keys.add(k)
    if seen_keys:
        print("Available tag keys:", ", ".join(sorted(seen_keys)))
    else:
        print("  (no frame tags at all)")
except Exception:
    print(all_tags if all_tags else "  (empty)")

print("\n=== Done. Interpret results: ===")
print("  timecode present   → PRIMARY detection works (100% reliable)")
print("  rec_date/rec_time  → FALLBACK detection works")
print("  neither            → must use scene detection")
