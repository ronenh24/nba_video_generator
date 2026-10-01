#!/usr/bin/env python3

import glob
import json
import os
import re
import subprocess
import sys
import unicodedata


# Directory containing MP4 files
VIDEO_DIRECTORY = os.getcwd()

# Where the agent writes thumbnails (orchestrator.THUMB_DIR)
THUMB_DIRECTORY = os.path.join(VIDEO_DIRECTORY, "thumbnails")

# Your existing upload script
UPLOAD_SCRIPT = "upload_videos.py"

STATE_FILE = "uploaded_videos.json"

# upload_videos.py exit code: video uploaded, thumbnail didn't.
EXIT_THUMBNAIL_FAILED = 2

NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def _load_state() -> set:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def _save_state(state: set) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(state), f, indent=2)


def _stem(filename: str) -> str:
    """'Foo.mp4' -> 'Foo'. (str.strip(".mp4") strips *characters*, so it
    would also eat a leading/trailing m, p, 4 or '.' from the name itself.)"""
    return os.path.splitext(filename)[0]


def _description_path(video: str) -> str:
    return os.path.join(VIDEO_DIRECTORY, _stem(video) + " description.txt")


def _thumbnail_path(video: str) -> str:
    return os.path.join(THUMB_DIRECTORY, _stem(video) + ".jpg")


def _remove(path: str | None) -> None:
    if path and os.path.exists(path):
        os.remove(path)


def upload_videos():
    processed = _load_state()

    mp4_files = []

    for f in os.listdir(VIDEO_DIRECTORY):
        if not f.lower().endswith(".mp4"):
            continue

        file_path = os.path.join(VIDEO_DIRECTORY, f)

        if f in processed:
            os.remove(file_path)
            _remove(_description_path(f))
            _remove(_thumbnail_path(f))
        else:
            mp4_files.append(f)

    mp4_files.sort()

    if not mp4_files:
        print("No MP4 files found.")
        return

    print("Found %d MP4 files." % len(mp4_files))

    used_thumbs = set()

    for number, video in enumerate(mp4_files, 1):
        print()
        print("=" * 60)
        print("Uploading %d/%d" % (number, len(mp4_files)))
        print("File:", video)
        print("=" * 60)

        with open(_description_path(video), "r", encoding="utf-8") as f:
            description = "\n".join(f.readlines())
        description = "#nba\n\n" + description

        command = [
            sys.executable,
            UPLOAD_SCRIPT,
            "--file",
            video,
            "--title",
            _stem(video),
            "--description",
            description,
            "--keywords",
            "nba"
        ]

        thumbnail = _thumbnail_path(video)

        if thumbnail:
            print("Thumbnail:", os.path.basename(thumbnail))
            used_thumbs.add(thumbnail)
            command += ["--thumbnail", thumbnail]
        else:
            print("Thumbnail: none found in", THUMB_DIRECTORY)

        result = subprocess.run(command)

        if result.returncode in (0, EXIT_THUMBNAIL_FAILED):
            print("Upload completed:", video)
            processed.add(video)
            os.remove(os.path.join(VIDEO_DIRECTORY, video))
            _remove(_description_path(video))

            if result.returncode == 0:
                _remove(thumbnail)
            else:
                print("Thumbnail was NOT set; kept file:", thumbnail)
        else:
            print("Upload FAILED:", video)
            print("Continuing to next video...")

    print()
    print("All files processed.")

    _save_state(processed)


if __name__ == "__main__":
    upload_videos()
