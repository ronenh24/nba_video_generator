"""Chrome driver and in-browser clip downloading."""
import os
import re
import time
from contextlib import contextmanager
from urllib.parse import urlparse

from selenium import webdriver

from .media import download_media, resolve_video_url


HEADLESS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


def make_driver(headless: bool = False):
    opts = webdriver.ChromeOptions()
    if headless:
        # Exactly the options known to work headless.
        opts.add_argument("--headless=new")
        opts.add_argument("--log-level=3")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(f"--user-agent={HEADLESS_USER_AGENT}")
    else:
        opts.add_argument("--window-size=1280,900")
        opts.add_argument("--mute-audio")
        opts.add_argument("--disable-blink-features=AutomationControlled")
    # lets get_pbp_browser read the page's own network responses
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(options=opts)


def safe_name(text: str, n: int = 45) -> str:
    """Filename-safe but keeps spaces; only strips characters
    illegal in filenames."""
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", text)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:n].strip(" ._")


def download_plays(driver, base_name, result: list, max_retries: int = 3):
    """
    result: list of (videoeventsasset_url, description, event_id, score).
    Returns [(saved_path, description), ...] in input order.
    """
    i = 0
    player_urls = []

    download_dir = os.path.abspath(str(base_name))
    os.makedirs(download_dir, exist_ok=True)
    del driver

    for asset_url, desc_raw, _, _ in result:
        saved = False

        for attempt in range(1, max_retries + 1):
            try:
                print(
                    f"Clip {i}: attempt {attempt}/{max_retries}  ({desc_raw})"
                )

                src = resolve_video_url(asset_url)

                clip_name = os.path.basename(urlparse(src).path)

                if not clip_name.endswith(".mp4"):
                    clip_name = f"video_{i}.mp4"

                clip_name = f"{i:02d}_{clip_name}"  # unique + keeps game order
                save_path = os.path.join(download_dir, clip_name)

                print(f"Downloading: {clip_name}")

                download_media(src, save_path)

                player_urls.append((save_path, desc_raw))
                i += 1
                saved = True

                print(f"Successfully downloaded: {clip_name}")
                break

            except Exception as e:
                print(f"Clip attempt {attempt} failed: {e}")

                if attempt < max_retries:
                    time.sleep(2 * attempt)

        if not saved:
            print(
                f"Skipping clip after {max_retries} failed attempts: "
                f"{asset_url}"
            )

        time.sleep(3)

    return player_urls


@contextmanager
def open_browser(headless: bool = False):
    """`with open_browser() as driver:` - always quits Chrome afterwards."""
    driver = make_driver(headless)
    try:
        yield driver
    finally:
        driver.quit()
