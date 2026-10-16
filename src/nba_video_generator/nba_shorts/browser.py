"""Chrome driver and in-browser clip downloading."""
import base64
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

JS_FETCH_B64 = """
var url = arguments[0];
var callback = arguments[arguments.length - 1];
fetch(url)
  .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.blob(); })
  .then(blob => {
      if (blob.size === 0) throw new Error("Downloaded video is empty");
      var reader = new FileReader();
      reader.onloadend = function() {
          if (reader.error) { callback("ERROR: " + reader.error); return; }
          callback(reader.result.split(",")[1]);
      };
      reader.readAsDataURL(blob);
  })
  .catch(err => callback("ERROR: " + err.message));
"""


def make_driver(headless: bool = False):
    opts = webdriver.ChromeOptions()
    if headless:  # often fails to load the NBA video player; off by default
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--mute-audio")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(options=opts)


def safe_name(text: str, n: int = 45) -> str:
    """Filename-safe but keeps spaces; only strips characters illegal in filenames."""
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", text)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:n].strip(" ._")


def download_plays(driver, out_dir: Path, result: list, max_retries: int = 3):
    """
    result: list of (page_url, description, event_id, score).
    Returns list of (saved_path, description) in input order.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_clips = []
    first_page = True

    for page_url, desc, eid, score in result:
        saved = False
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[{eid}] {desc}  (attempt {attempt}/{max_retries})")
                driver.get(page_url)

                WebDriverWait(driver, 30).until(
                    lambda d: d.find_element(By.TAG_NAME, "body").text.strip() != "")
                body = driver.find_element(By.TAG_NAME, "body").text.lower()
                if "content unavailable" in body or "no video available" in body:
                    raise RuntimeError("clip is unavailable on nba.com")

                if first_page:  # dismiss the consent/modal once
                    try:
                        driver.find_element(By.CSS_SELECTOR,
                                            'button[aria-label="Close"]').click()
                    except Exception:
                        pass
                    first_page = False

                video = WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "video.vjs-tech")))
                driver.execute_script("arguments[0].pause();", video)

                # src can populate a moment after the element appears
                src = None
                for _ in range(20):
                    src = video.get_attribute("src")
                    if src and src.startswith("http"):
                        break
                    time.sleep(0.5)
                if not src or src.endswith("missing.mp4"):
                    raise RuntimeError("video source is missing or invalid")

                try:
                    driver.find_element(By.CSS_SELECTOR,
                                        'button[data-click="close"]').click()
                except Exception:
                    pass

                save_path = out_dir / f"{int(eid):04d}_{safe_name(desc, 60)}.mp4"
                print(f"      downloading -> {save_path.name}")

                driver.set_script_timeout(120)
                b64 = driver.execute_async_script(JS_FETCH_B64, src)
                if not b64 or b64.startswith("ERROR:"):
                    raise RuntimeError(f"fetch failed: {b64}")
                data = base64.b64decode(b64, validate=True)
                if len(data) < 10_000:
                    raise RuntimeError("downloaded file suspiciously small")

                tmp = save_path.with_suffix(".part")
                try:
                    tmp.write_bytes(data)
                    os.replace(tmp, save_path)
                finally:
                    if tmp.exists():
                        tmp.unlink()

                saved_clips.append((save_path, desc))
                saved = True
                print(f"      ok ({len(data) / 1e6:.1f} MB)")
                break

            except Exception as e:
                print(f"      attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)

        if not saved:
            print(f"      skipping [{eid}] after {max_retries} failed attempts")
        time.sleep(2)

    return saved_clips



@contextmanager
def open_browser(headless: bool = False):
    """`with open_browser() as driver:` - always quits Chrome afterwards."""
    driver = make_driver(headless)
    try:
        yield driver
    finally:
        driver.quit()
