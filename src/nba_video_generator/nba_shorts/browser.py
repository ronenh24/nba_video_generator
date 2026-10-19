"""Chrome driver and in-browser clip downloading."""
import base64
import os
import re
import time
from contextlib import contextmanager

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

JS_FETCH_B64 = """
var url = arguments[0];
var callback = arguments[arguments.length - 1];

fetch(url)
    .then(response => {
        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }
        return response.blob();
    })
    .then(blob => {
        if (blob.size === 0) {
            throw new Error("Downloaded video is empty");
        }

        var reader = new FileReader();
        reader.onloadend = function() {
            if (reader.error) {
                callback("ERROR: " + reader.error);
                return;
            }

            callback(reader.result.split(",")[1]);
        };
        reader.readAsDataURL(blob);
    })
    .catch(err => callback("ERROR: " + err.message));
"""


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
    result: list of (page_url, description, event_id, score).
    Returns [(saved_path, description), ...] in input order.
    Page handling matches the version known to work headless.
    """
    i = 0
    player_urls = []

    download_dir = os.path.abspath(str(base_name))
    os.makedirs(download_dir, exist_ok=True)

    for video_url, desc_raw, _, _ in result:
        saved = False

        for attempt in range(1, max_retries + 1):
            try:
                print(
                    f"Clip {i}: attempt {attempt}/{max_retries}  ({desc_raw})"
                )

                # Reload the clip page on every attempt to obtain
                # a fresh video URL if the previous URL has expired.
                driver.get(video_url)

                WebDriverWait(driver, 30).until(
                    lambda d: d.find_element(By.TAG_NAME, "body").text.lower()
                    and True
                )

                body = driver.find_element(By.TAG_NAME, "body").text.lower()

                if "content unavailable" in body or\
                        "no video available" in body:
                    raise RuntimeError("Clip is unavailable")

                if i == 0 and attempt == 1:
                    try:
                        driver.find_element(
                            By.CSS_SELECTOR,
                            'button[aria-label="Close"]'
                        ).click()
                    except Exception:
                        pass

                video = WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "video.vjs-tech")
                    )
                )

                driver.execute_script("arguments[0].pause();", video)

                src = video.get_attribute("src")

                if not src or src.endswith("missing.mp4"):
                    raise RuntimeError("Video source is missing or invalid")

                try:
                    driver.find_element(
                        By.CSS_SELECTOR, 'button[data-click="close"]'
                    ).click()
                except Exception:
                    pass

                clip_name = src.split("/")[-1].split("?")[0]

                if not clip_name.endswith(".mp4"):
                    clip_name = f"video_{i}.mp4"

                clip_name = f"{i:02d}_{clip_name}"  # unique + keeps game order
                save_path = os.path.join(download_dir, clip_name)

                print(f"Downloading: {clip_name}")

                driver.set_script_timeout(120)
                base64_data = driver.execute_async_script(JS_FETCH_B64, src)

                if not base64_data or base64_data.startswith("ERROR:"):
                    raise RuntimeError(f"Fetch failed: {base64_data}")

                video_bytes = base64.b64decode(base64_data, validate=True)

                if not video_bytes:
                    raise RuntimeError("Empty video data")

                # Write to a temporary file first so a failed
                # attempt cannot leave a partial final file.
                temp_path = save_path + ".part"

                try:
                    with open(temp_path, "wb") as f:
                        f.write(video_bytes)

                    os.replace(temp_path, save_path)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                player_urls.append((save_path, desc_raw))
                i += 1
                saved = True

                print(f"Successfully downloaded: {clip_name}")
                break

            except Exception as e:
                print(f"Clip attempt {attempt} failed: {e}")

                if attempt < max_retries:
                    time.sleep(2 * attempt)

                    try:
                        driver.delete_all_cookies()
                        driver.refresh()
                    except Exception:
                        pass

        if not saved:
            print(
                f"Skipping clip after {max_retries} failed attempts: "
                f"{video_url}"
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
