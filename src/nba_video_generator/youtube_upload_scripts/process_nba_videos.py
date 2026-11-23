#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# upload_videos.py exit code: video uploaded, thumbnail didn't.
EXIT_THUMBNAIL_FAILED = 2

DEFAULT_MUSIC_DIRECTORY = (
    Path.home() / "Videos" / "nba_videos" / "music"
)
MUSIC_EXTENSIONS = {
    ".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".webm",
}


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _ffmpeg_tools(ffmpeg_path: str | None = None) -> tuple[Path, Path]:
    configured_ffmpeg = ffmpeg_path or os.environ.get("FFMPEG_PATH")
    if configured_ffmpeg:
        ffmpeg = Path(configured_ffmpeg).expanduser()
        if not ffmpeg.is_file():
            raise FileNotFoundError(f"FFmpeg not found: {ffmpeg}")
    else:
        bundled_ffmpeg = (
            Path(__file__).resolve().parents[1]
            / "ffmpeg-9.0.2-essentials_build"
            / "bin"
            / "ffmpeg.exe"
        )
        ffmpeg = bundled_ffmpeg if bundled_ffmpeg.is_file() else Path(
            shutil.which("ffmpeg") or ""
        )
        if not str(ffmpeg) or not ffmpeg.is_file():
            raise FileNotFoundError(
                "FFmpeg not found. Set FFMPEG_PATH or install FFmpeg."
            )

    ffprobe_name = "ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe"
    ffprobe = ffmpeg.with_name(ffprobe_name)
    if not ffprobe.is_file():
        path_probe = shutil.which("ffprobe")
        if path_probe:
            ffprobe = Path(path_probe)
        else:
            raise FileNotFoundError(f"FFprobe not found beside FFmpeg: {ffprobe}")
    return ffmpeg, ffprobe


def _has_audio_stream(ffprobe: Path, media_file: Path) -> bool:
    result = subprocess.run(
        [
            str(ffprobe), "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0",
            str(media_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def _media_duration(ffprobe: Path, media_file: Path) -> float:
    result = subprocess.run(
        [
            str(ffprobe), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(media_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Could not determine video duration: {media_file}") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"Invalid video duration for {media_file}: {duration}")
    return duration


def _silent_intervals(
    ffmpeg: Path,
    ffprobe: Path,
    video: Path,
    duration: float,
    has_audio: bool | None = None,
) -> list[tuple[float, float]]:
    if has_audio is None:
        has_audio = _has_audio_stream(ffprobe, video)
    if not has_audio:
        return [(0.0, duration)]

    result = subprocess.run(
        [
            str(ffmpeg), "-hide_banner", "-nostats", "-i", str(video),
            "-af", "silencedetect=noise=-50dB:d=0.5", "-f", "null",
            os.devnull,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    intervals: list[tuple[float, float]] = []
    silence_start = None
    for line in result.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*(-?\d+(?:\.\d+)?)", line)
        if start_match:
            silence_start = max(0.0, float(start_match.group(1)))
        end_match = re.search(r"silence_end:\s*(-?\d+(?:\.\d+)?)", line)
        if end_match and silence_start is not None:
            silence_end = min(duration, float(end_match.group(1)))
            if silence_end > silence_start:
                intervals.append((silence_start, silence_end))
            silence_start = None
    if silence_start is not None and duration > silence_start:
        intervals.append((silence_start, duration))
    return intervals


def _add_music_to_silent_parts(
    video: Path,
    music_files: list[Path],
    ffmpeg: Path,
    ffprobe: Path,
) -> Path | None:
    duration = _media_duration(ffprobe, video)
    has_audio = _has_audio_stream(ffprobe, video)
    intervals = _silent_intervals(ffmpeg, ffprobe, video, duration, has_audio)
    if not intervals:
        return None

    music = random.choice(music_files)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{video.stem}_music_",
        suffix=video.suffix,
        dir=video.parent,
    )
    os.close(file_descriptor)
    temporary_video = Path(temporary_name)
    try:
        command = [str(ffmpeg), "-y", "-loglevel", "error", "-i", str(video)]
        if has_audio:
            enabled_intervals = "+".join(
                f"between(t\\,{start:.3f}\\,{end:.3f})"
                for start, end in intervals
            )
            command.extend([
                "-stream_loop", "-1", "-i", str(music),
                "-filter_complex",
                f"[1:a:0]volume=0:enable='not({enabled_intervals})',"
                f"volume=0.20:enable='{enabled_intervals}'[music];"
                "[0:a:0][music]amix=inputs=2:duration=first:"
                "dropout_transition=0:normalize=0[aout]",
                "-map", "0:v:0", "-map", "[aout]",
            ])
        else:
            command.extend([
                "-stream_loop", "-1", "-i", str(music),
                "-af", "volume=0.20", "-map", "0:v:0", "-map", "1:a:0",
            ])
        command.extend([
            "-t", f"{duration:.3f}", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "192k", "-movflags", "+faststart", str(temporary_video),
        ])
        subprocess.run(command, check=True)
    except Exception:
        temporary_video.unlink(missing_ok=True)
        raise
    print(
        f"Added {music.name} to {len(intervals)} silent section(s) "
        f"in {video.name}."
    )
    return temporary_video


def upload_videos(
    video_directory: str,
    client_secrets_file: str,
    playlists: list[str] | None = None,
    privacy_status: str = "private",
    delete_uploaded: bool = False,
    music_directory: str | None = None,
    ffmpeg_path: str | None = None,
) -> int:
    """Upload MP4s from a folder, with optional descriptions and thumbnails."""
    _configure_console_encoding()
    video_dir = Path(video_directory).expanduser().resolve(strict=True)
    secrets_path = Path(client_secrets_file).expanduser().resolve(strict=True)
    if not video_dir.is_dir():
        raise NotADirectoryError(f"Upload folder is not a directory: {video_dir}")
    if not secrets_path.is_file():
        raise FileNotFoundError(f"Client secrets file not found: {secrets_path}")
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ValueError("Privacy must be private, unlisted, or public.")

    music_dir = Path(music_directory).expanduser() if music_directory else DEFAULT_MUSIC_DIRECTORY
    music_dir = music_dir.resolve(strict=True)
    if not music_dir.is_dir():
        raise NotADirectoryError(f"Music folder is not a directory: {music_dir}")
    ffmpeg, ffprobe = _ffmpeg_tools(ffmpeg_path)
    music_files = sorted(
        path for path in music_dir.iterdir()
        if path.is_file() and path.suffix.lower() in MUSIC_EXTENSIONS
        and _has_audio_stream(ffprobe, path)
    )
    if not music_files:
        raise FileNotFoundError(
            f"No supported audio tracks found in {music_dir}."
        )

    videos = sorted(
        (
            path for path in video_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".mp4"
        ),
        key=lambda path: path.stat().st_mtime,
    )
    if not videos:
        raise FileNotFoundError(f"No MP4 videos found in {video_dir}.")

    secrets_key = hashlib.sha256(
        str(secrets_path).casefold().encode("utf-8")
    ).hexdigest()[:16]
    token_dir = Path.home() / ".nba_video_generator" / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_file = token_dir / f"youtube-{secrets_key}.json"
    upload_script = Path(__file__).with_name("upload_videos.py")
    thumbnail_dir = video_dir # / "thumbnails"
    playlist_ids = ["PLMUQgUVnh3jw"] if playlists is None else playlists
    failures = []

    print(f"Found {len(videos)} MP4 video(s).")
    for number, video in enumerate(videos, 1):
        print(f"\n{'=' * 60}\nUploading {number}/{len(videos)}\nFile: {video.name}\n{'=' * 60}")
        description_file = video.with_name(f"{video.stem} description.txt")
        description = ""
        if description_file.is_file():
            description = description_file.read_text(encoding="utf-8")
        description = "#nba\n\n" + description
        thumbnail = thumbnail_dir / f"{video.stem}.jpg"

        temporary_video = _add_music_to_silent_parts(
            video, music_files, ffmpeg, ffprobe
        )
        upload_file = temporary_video or video
        command = [
            sys.executable,
            str(upload_script),
            "--file", str(upload_file),
            "--client-secrets", str(secrets_path),
            "--token-file", str(token_file),
            "--title", video.stem,
            "--description", description,
            "--keywords", "nba",
            "--privacyStatus", privacy_status,
        ]
        if playlist_ids:
            command.extend(["--playlists", *playlist_ids])
        if thumbnail.is_file():
            command.extend(["--thumbnail", str(thumbnail)])
            print(f"Thumbnail: {thumbnail.name}")
        else:
            print("Thumbnail: none found")

        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                check=False,
            )
        finally:
            if temporary_video is not None:
                temporary_video.unlink(missing_ok=True)
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)

        if result.returncode in (0, EXIT_THUMBNAIL_FAILED):
            print(f"Upload completed: {video.name}")
            if result.returncode == EXIT_THUMBNAIL_FAILED:
                print("Thumbnail was not set; local files were kept.")
            elif delete_uploaded:
                video.unlink()
                description_file.unlink(missing_ok=True)
                thumbnail.unlink(missing_ok=True)
        else:
            failures.append(video.name)
            print(f"Upload FAILED: {video.name}; continuing to next video.")

    if failures:
        raise RuntimeError(
            f"Upload failed for {len(failures)} video(s): {', '.join(failures)}"
        )
    print(f"\nAll {len(videos)} video(s) uploaded successfully.")
    return len(videos)


if __name__ == '__main__':
    import argparse

    _configure_console_encoding()
    parser = argparse.ArgumentParser(
        description="Upload videos from a folder to YouTube."
    )
    parser.add_argument(
        "--folder",
        default=os.getcwd(),
        help="Folder containing MP4 files (default: current directory)",
    )
    parser.add_argument(
        "--client-secrets",
        required=True,
        help="Google OAuth client secrets JSON file",
    )
    parser.add_argument(
        "--playlists",
        nargs='+',
        type=str,
        default=["PLMUQgUVnh3jw"],
        help="Optional list of YouTube playlist IDs to add the video to (e.g., --playlists PL1 PL2)"
    )
    parser.add_argument(
        "--privacy",
        choices=("private", "unlisted", "public"),
        default="private",
        help="Video privacy status",
    )
    parser.add_argument(
        "--delete-uploaded",
        action="store_true",
        help="Delete videos and descriptions after a successful upload",
    )
    parser.add_argument(
        "--music-folder",
        default=str(DEFAULT_MUSIC_DIRECTORY),
        help="Folder of licensed audio tracks used in silent video sections",
    )

    args = parser.parse_args()

    upload_videos(
        args.folder,
        args.client_secrets,
        args.playlists,
        args.privacy,
        args.delete_uploaded,
        args.music_folder,
    )
