import argparse
import subprocess
import sys
import time
from pathlib import Path


def fmt_ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def cmd_to_str(cmd: list[str]) -> str:
    return " ".join(f'"{a}"' if " " in a else a for a in cmd)


def build_cmd(src: Path, dst: Path, crf: int, preset: str, deinterlace: bool) -> list[str]:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
    ]

    if deinterlace:
        cmd += ["-vf", "bwdif=mode=send_field,format=yuv420p"]
    else:
        cmd += ["-flags", "+ildct+ilme"]

    cmd += [
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-tune", "film",
        "-profile:v", "high",
        "-level", "4.1",
        "-pix_fmt", "yuv420p",
        "-color_primaries", "5",
        "-color_trc", "5",
        "-colorspace", "5",
        "-color_range", "tv",
        "-c:a", "aac",
        "-b:a", "320k",
        "-movflags", "+faststart",
        str(dst),
    ]
    return cmd


def resolve_output(input_path: Path, output_arg: str) -> Path:
    out = Path(output_arg)
    video_exts = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
    if out.suffix.lower() in video_exts or out.name.find(".") != -1:
        return out
    return out / input_path.with_suffix(".mp4").name


def main():
    parser = argparse.ArgumentParser(
        description="Recursively convert DV-AVI files to visually lossless H.264 MP4. "
                    "Accepts a single .avi file or a directory."
    )
    parser.add_argument("input", help=".avi file or directory to scan for .avi files")
    parser.add_argument("output", help="Output .mp4 path (for single file) or output directory")
    parser.add_argument("--crf", type=int, default=16,
                        help="x264 CRF (0-51, lower=better, 16=visually lossless)")
    parser.add_argument("--preset", default="slow",
                        choices=["ultrafast","superfast","veryfast","faster","fast",
                                 "medium","slow","slower","veryslow","placebo"],
                        help="x264 preset (default: slow)")
    parser.add_argument("--deinterlace", action="store_true", default=True,
                        help="Deinterlace to 50fps progressive (default)")
    parser.add_argument("--no-deinterlace", dest="deinterlace", action="store_false",
                        help="Keep interlaced video")
    parser.add_argument("--dry-run", action="store_true",
                        help="List files without encoding")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-encode even if output .mp4 exists")

    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_arg = args.output

    if input_path.is_file():
        if input_path.suffix.lower() != ".avi":
            print(f"Error: single-file mode requires an .avi file, got: {input_path}")
            sys.exit(1)

        dst = resolve_output(input_path, output_arg).resolve()

        if dst.exists() and not args.overwrite:
            print(f"Output already exists: {dst}\nUse --overwrite to re-encode.")
            sys.exit(0)

        deint_label = "deinterlaced" if args.deinterlace else "interlaced"
        print(f"Input:  {input_path}")
        print(f"Output: {dst}")
        print(f"Settings: CRF={args.crf}, preset={args.preset}, {deint_label}, aac 320k")

        if args.dry_run:
            cmd = build_cmd(input_path, dst, args.crf, args.preset, args.deinterlace)
            print(cmd_to_str(cmd))
            sys.exit(0)

        dst.parent.mkdir(parents=True, exist_ok=True)

        print("Encoding...", end=" ", flush=True)
        start = time.time()
        proc = subprocess.run(
            build_cmd(input_path, dst, args.crf, args.preset, args.deinterlace),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        elapsed = time.time() - start

        if proc.returncode != 0:
            print(f"FAILED ({fmt_ts(elapsed)})")
            stderr = (proc.stderr or "").strip()
            if stderr:
                for line in stderr.splitlines():
                    if "Error" in line or "error" in line or "failed" in line.lower():
                        print(f"  {line.strip()[:150]}")
            dst.unlink(missing_ok=True)
            sys.exit(1)

        in_mb = input_path.stat().st_size / (1024 * 1024)
        out_mb = dst.stat().st_size / (1024 * 1024)
        ratio = (1 - out_mb / in_mb) * 100 if in_mb else 0
        print(f"OK  {in_mb:.0f} -> {out_mb:.0f} MB  "
              f"({ratio:.0f}% saved, {fmt_ts(elapsed)})")
        print("Done.")
        sys.exit(0)

    src_root = input_path
    dst_root = Path(output_arg).resolve()

    if not src_root.is_dir():
        print(f"Error: input not found: {src_root}")
        sys.exit(1)

    avi_files = sorted(src_root.rglob("*.avi"))
    if not avi_files:
        print(f"No .avi files found under: {src_root}")
        sys.exit(0)

    tasks = []
    skipped = 0
    for avi in avi_files:
        rel = avi.relative_to(src_root)
        mp4 = dst_root / rel.with_suffix(".mp4")
        if mp4.exists() and not args.overwrite:
            skipped += 1
            continue
        tasks.append((avi, mp4, rel))

    if not tasks:
        print(f"All {skipped} .mp4 files already exist. Use --overwrite to re-encode.")
        sys.exit(0)

    total = len(tasks)
    print(f"Found {len(avi_files)} .avi file(s), {skipped} already done, {total} to encode.")
    if args.dry_run:
        for avi, mp4, rel in tasks:
            cmd = build_cmd(avi, mp4, args.crf, args.preset, args.deinterlace)
            print(cmd_to_str(cmd))
        print(f"\n{total} command(s) above. Run without --dry-run to execute.")
        sys.exit(0)

    dst_root.mkdir(parents=True, exist_ok=True)

    deint_label = "deinterlaced" if args.deinterlace else "interlaced"
    print(f"Settings: CRF={args.crf}, preset={args.preset}, {deint_label}, aac 320k")
    print(f"Output: {dst_root}\n")

    failed = 0
    total_start = time.time()

    for idx, (avi, mp4, rel) in enumerate(tasks, 1):
        mp4.parent.mkdir(parents=True, exist_ok=True)

        rel_str = str(rel)
        print(f"[{idx}/{total}] {rel_str}", end=" ", flush=True)

        file_start = time.time()
        cmd = build_cmd(avi, mp4, args.crf, args.preset, args.deinterlace)

        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

        elapsed = time.time() - file_start

        if proc.returncode != 0:
            print(f"FAILED ({fmt_ts(elapsed)})")
            stderr = (proc.stderr or "").strip()
            if stderr:
                for line in stderr.splitlines():
                    if "Error" in line or "error" in line or "failed" in line.lower():
                        print(f"  {line.strip()[:150]}")
            mp4.unlink(missing_ok=True)
            failed += 1
        else:
            in_mb = avi.stat().st_size / (1024 * 1024)
            out_mb = mp4.stat().st_size / (1024 * 1024)
            ratio = (1 - out_mb / in_mb) * 100 if in_mb else 0
            print(f"OK  {in_mb:.0f} -> {out_mb:.0f} MB  "
                  f"({ratio:.0f}% saved, {fmt_ts(elapsed)})")

    total_elapsed = time.time() - total_start
    ok = total - failed
    print(f"\nDone. {ok} succeeded, {failed} failed, total time {fmt_ts(total_elapsed)}.")


if __name__ == "__main__":
    main()
