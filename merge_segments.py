import subprocess
import sys
from pathlib import Path

SRC = Path(sys.argv[1])
K = int(sys.argv[2])

files = sorted(SRC.parent.glob("*.avi"), key=lambda p: p.name)
idx = files.index(SRC)
group = files[idx:idx + K]

print(f"Merging {K} files starting from {SRC.name}:\n")
for f in group:
    print(f"  {f.name}")

tmp = SRC.parent / "_concat.txt"
tmp.write_text("\n".join(f"file '{f.resolve()}'" for f in group), encoding="utf-8")

out = SRC.parent / f"{SRC.stem}_plus{K-1}{SRC.suffix}"
subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp),
                "-c", "copy", "-map", "0", str(out)],
               capture_output=False)
tmp.unlink()

print(f"\n-> {out.name}")
