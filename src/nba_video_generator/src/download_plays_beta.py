"""
Downloads each play.
"""

import os
import time
from urllib.parse import urlparse

from selenium import webdriver

from nba_video_generator.nba_shorts.media import (
    download_media, resolve_video_url,
)


def download_plays(driver: webdriver, base_name: str,
                   result: list, max_retries: int = 3):
    """Downloads each play."""
    i = 0
    player_urls = []

    download_dir = os.path.abspath(base_name)
    os.makedirs(download_dir, exist_ok=True)
    del driver

    for asset_url, desc_raw, _, _ in result:
        saved = False

        for attempt in range(1, max_retries + 1):
            try:
                print(
                    f"Clip {i}: attempt {attempt}/{max_retries}"
                )

                src = resolve_video_url(asset_url)

                clip_name = os.path.basename(urlparse(src).path)

                if not clip_name.endswith(".mp4"):
                    clip_name = f"video_{i}.mp4"

                save_path = os.path.join(
                    download_dir, clip_name
                )

                print(f"Downloading: {clip_name}")

                download_media(src, save_path)

                player_urls.append((save_path, desc_raw))
                i += 1
                saved = True

                print(f"Successfully downloaded: {clip_name}")
                break

            except Exception as e:
                print(
                    f"Clip attempt {attempt} failed: {e}"
                )

                if attempt < max_retries:
                    time.sleep(2 * attempt)

        if not saved:
            print(
                f"Skipping clip after {max_retries} failed attempts: "
                f"{asset_url}"
            )

        time.sleep(3)

    return player_urls
