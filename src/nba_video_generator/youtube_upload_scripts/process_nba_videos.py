#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path


# upload_videos.py exit code: video uploaded, thumbnail didn't.
EXIT_THUMBNAIL_FAILED = 2


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def upload_videos(
    video_directory: str,
    client_secrets_file: str,
    playlists: list[str] | None = None,
    privacy_status: str = "private",
    delete_uploaded: bool = False,
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
    thumbnail_dir = video_dir / "thumbnails"
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

        command = [
            sys.executable,
            str(upload_script),
            "--file", str(video),
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
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
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

    args = parser.parse_args()

    upload_videos(
        args.folder,
        args.client_secrets,
        args.playlists,
        args.privacy,
        args.delete_uploaded,
    )
