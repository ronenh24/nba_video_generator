"""ffmpeg helpers: 9:16 conversion and compilation."""
import os
import subprocess
from pathlib import Path


def need_ffmpeg(ffmpeg_path: str):
    if not os.path.exists(ffmpeg_path) or not\
            ffmpeg_path.endswith("ffmpeg.exe"):
        print(os.path.exists(ffmpeg_path))
        raise RuntimeError("ffmpeg not found")


def to_vertical(src: Path, dst: Path, ffmpeg_path: str):
    """1080x1920 with blurred background so the action isn't cropped away."""
    vf = ("[0:v]split[a][b];"
          "[a]scale=1080:1920:force_original_aspect_ratio=increase,"
          "crop=1080:1920,boxblur=25:5[bg];"
          "[b]scale=1080:-2[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]")
    subprocess.run(
        [ffmpeg_path, "-y", "-loglevel", "error", "-i", str(src),
         "-filter_complex", vf, "-map", "[v]", "-map", "0:a?",
         "-c:v", "libx264", "-crf", "20", "-r", "30",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", str(dst)],
        check=True
    )


def compile_clips(clips: list, dst: Path, ffmpeg_path: str, title: str = ""):
    """Concat clips. Re-encodes so mixed sources never glitch."""
    lst = dst.with_suffix(".txt")

    def q(c):  # escape single quotes for the ffmpeg concat list
        return Path(c).resolve().as_posix().replace("'", "'\\''")
    lst.write_text(
        "".join("file '" + q(c) + "'\n" for c in clips),
        encoding="utf-8"
    )
    try:
        subprocess.run(
            [ffmpeg_path, "-y", "-loglevel", "error", "-f", "concat",
             "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-crf", "20",
             "-c:a", "aac", "-pix_fmt", "yuv420p"]
            + (["-metadata", f"title={title}"] if title else [])
            + [str(dst)], check=True)
    finally:
        lst.unlink(missing_ok=True)
