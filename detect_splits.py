import argparse
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path


def ffprobe(video: str, args: list[str]) -> str:
    cmd = ["ffprobe", "-v", "quiet"] + args + [video]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def get_video_info(video: str) -> dict:
    fps_str = ffprobe(video, [
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "csv=p=0"
    ])
    fps = float(Fraction(fps_str)) if fps_str else 25.0

    dur_str = ffprobe(video, [
        "-select_streams", "v:0",
        "-show_entries", "stream=duration",
        "-of", "csv=p=0"
    ])
    if not dur_str or dur_str == "N/A":
        dur_str = ffprobe(video, [
            "-show_entries", "format=duration",
            "-of", "csv=p=0"
        ])
    duration = float(dur_str) if dur_str and dur_str != "N/A" else 0.0

    w_str = ffprobe(video, [
        "-select_streams", "v:0",
        "-show_entries", "stream=width",
        "-of", "csv=p=0"
    ])
    h_str = ffprobe(video, [
        "-select_streams", "v:0",
        "-show_entries", "stream=height",
        "-of", "csv=p=0"
    ])
    codec = ffprobe(video, [
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name",
        "-of", "csv=p=0"
    ])

    return {
        "path": str(Path(video).resolve()),
        "codec": codec,
        "fps": fps,
        "duration": duration,
        "width": int(w_str) if w_str else 0,
        "height": int(h_str) if h_str else 0,
        "total_frames": int(round(duration * fps)) if duration else 0,
    }


def detect_by_scene(video: str, threshold: float) -> list[dict]:
    cmd = [
        "ffmpeg", "-i", video,
        "-filter:v",
        f"select='gt(scene\\,{threshold})',showinfo",
        "-vsync", "vfr",
        "-an",
        "-f", "null", "-"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    stderr = proc.stderr or ""

    splits = []
    pts_re = re.compile(r"pts_time:(\S+)")
    for line in stderr.splitlines():
        if "Parsed_showinfo" not in line:
            continue
        m = pts_re.search(line)
        if not m:
            continue
        seconds = float(m.group(1))
        if seconds > 0:
            splits.append(seconds)

    if not splits:
        return []

    seen: set[float] = set()
    uniq: list[float] = []
    for t in splits:
        key = round(t, 3)
        if key not in seen:
            seen.add(key)
            uniq.append(round(t, 3))
    uniq.sort()

    return [
        {
            "index": i,
            "seconds": t,
            "method": "scene",
            "confidence": "medium",
            "detail": f"Scene change at {_fmt_ts(t)}"
        }
        for i, t in enumerate(uniq)
    ]


def merge_nearby_splits(points: list[dict], min_gap: float) -> list[dict]:
    if not points or len(points) <= 1:
        return points

    merged = [points[0]]
    for curr in points[1:]:
        prev = merged[-1]
        gap = curr["seconds"] - prev["seconds"]
        if gap < min_gap:
            prev["detail"] += f"; merged {_fmt_ts(curr['seconds'])} (gap={gap:.1f}s)"
            continue
        merged.append(curr)

    for i, p in enumerate(merged):
        p["index"] = i

    return merged


def _fmt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def print_header(video: str, info: dict, threshold: float, min_gap: float):
    print(f"Analyzing: {info['path']}")
    print(f"  Codec: {info['codec']}, {info['width']}x{info['height']}")
    print(f"  FPS: {info['fps']:.2f}, Duration: {info['duration']:.1f}s "
          f"({_fmt_ts(info['duration'])}), ~{info['total_frames']} frames")
    print(f"  Scene threshold: {threshold}, min segment gap: {min_gap}s")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Detect split points in a concatenated DV-AVI video using scene detection."
    )
    parser.add_argument("video", help="Path to the AVI video file")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON file path (default: print to stdout)")
    parser.add_argument("--scene-threshold", type=float, default=0.3,
                        help="Scene change sensitivity (0.0-1.0, lower = more cuts, default: 0.3)")
    parser.add_argument("--min-duration", type=float, default=2.0,
                        help="Minimum segment duration in seconds; nearby splits merged "
                             "(default: 2.0)")
    args = parser.parse_args()

    video = args.video
    if not Path(video).exists():
        print(f"Error: file not found: {video}")
        sys.exit(1)

    info = get_video_info(video)
    print_header(video, info, args.scene_threshold, args.min_duration)

    print("Running scene detection (this may take a few minutes)...")
    points = detect_by_scene(video, args.scene_threshold)

    if not points:
        print("No scene changes detected. Try lowering --scene-threshold (e.g., 0.2).")
        sys.exit(1)

    print(f"Raw scene changes: {len(points)}")

    points = merge_nearby_splits(points, args.min_duration)

    fps = info["fps"]
    enriched = []
    for p in points:
        enriched.append({
            "index": p["index"],
            "timestamp": _fmt_ts(p["seconds"]),
            "frame": int(round(p["seconds"] * fps)),
            "seconds": p["seconds"],
            "method": p["method"],
            "confidence": p["confidence"],
            "detail": p["detail"],
        })

    output = {
        "video": info,
        "params": {
            "scene_threshold": args.scene_threshold,
            "min_duration": args.min_duration,
        },
        "split_count": len(enriched),
        "splits": enriched,
    }

    json_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"Results written to: {args.output}")
    else:
        print(json_str)

    print(f"\nDetected {len(enriched)} split point(s).")


if __name__ == "__main__":
    main()
