import argparse
import json
import subprocess
import sys
from pathlib import Path


def fmt_ts(seconds: float) -> str:
    return f"{seconds:.3f}"


def fmt_ts_readable(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def start_to_fname(seconds: float) -> str:
    ms_total = int(round(seconds * 1000))
    h = ms_total // 3600000
    m = (ms_total % 3600000) // 60000
    s = (ms_total % 60000) // 1000
    ms = ms_total % 1000
    return f"{h:02d}{m:02d}{s:02d}{ms:03d}"


def main():
    parser = argparse.ArgumentParser(
        description="Losslessly split a DV-AVI video into segments based on split-points JSON."
    )
    parser.add_argument("video", help="Path to the original AVI video file")
    parser.add_argument("splits", help="Path to the split-points JSON file (from detect_splits.py)")
    parser.add_argument("--output-dir", "-d", default="segments",
                        help="Output directory for segment files (default: ./segments)")
    parser.add_argument("--prefix", "-p", default=None,
                        help="Prefix for output filenames (default: video filename)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print ffmpeg commands without executing them")

    args = parser.parse_args()

    video_path = Path(args.video)
    splits_path = Path(args.splits)

    if not video_path.exists():
        print(f"Error: video not found: {video_path}")
        sys.exit(1)
    if not splits_path.exists():
        print(f"Error: splits JSON not found: {splits_path}")
        sys.exit(1)

    data = json.loads(splits_path.read_text(encoding="utf-8"))
    video_info = data.get("video", {})
    all_splits = data.get("splits", [])
    duration = video_info.get("duration", 0)

    prefix = args.prefix or video_path.stem
    out_dir = Path(args.output_dir)

    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    cut_points = [0.0]
    for sp in all_splits:
        cut_points.append(sp["seconds"])
    cut_points.append(duration)

    segments = []
    for i in range(len(cut_points) - 1):
        start = cut_points[i]
        end = cut_points[i + 1]
        segments.append((i + 1, start, end))

    print(f"Video: {video_path}")
    print(f"Duration: {fmt_ts_readable(duration)}")
    print(f"Splits: {len(all_splits)} → {len(segments)} segments")
    print()

    for seg_idx, start, end in segments:
        out_name = f"{prefix}_{start_to_fname(start)}{video_path.suffix}"
        out_path = (out_dir / out_name).resolve()

        duration_seg = end - start

        cmd = [
            "ffmpeg",
            "-ss", fmt_ts(start),
            "-i", str(video_path.resolve()),
            "-to", fmt_ts(end - start),
            "-c", "copy",
            "-map", "0",
            "-y",
            str(out_path),
        ]

        print(f"[{seg_idx}] {fmt_ts_readable(start)} → {fmt_ts_readable(end)} "
              f"({duration_seg:.1f}s) → {out_name}")

        if args.dry_run:
            print("  (dry-run) " + " ".join(cmd))
            print()
            continue

        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

        if proc.returncode != 0:
            print(f"  ERROR: {proc.stderr.splitlines()[-1] if proc.stderr else 'unknown error'}")
            print()
        else:
            out_size = out_path.stat().st_size if out_path.exists() else 0
            mb = out_size / (1024 * 1024)
            print(f"  OK ({mb:.1f} MB)")
            print()

    print("Done.")


if __name__ == "__main__":
    main()
