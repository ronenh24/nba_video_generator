import os
import time
import base64

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def download_plays(
    driver: webdriver,
    base_name: str,
    result: list,
    max_retries: int = 3,
):
    i = 0
    player_urls = []

    download_dir = os.path.abspath(base_name)
    os.makedirs(download_dir, exist_ok=True)

    js_download_script = """
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

    for video_url, desc_raw, _, _ in result:
        saved = False

        for attempt in range(1, max_retries + 1):
            try:
                print(
                    f"Clip {i}: attempt {attempt}/{max_retries}"
                )

                # Reload the clip page on every attempt to obtain
                # a fresh video URL if the previous URL has expired.
                driver.get(video_url)

                WebDriverWait(driver, 30).until(
                    lambda d: d.find_element(
                        By.TAG_NAME, "body"
                    ).text.lower()
                    and True
                )

                body = driver.find_element(
                    By.TAG_NAME, "body"
                ).text.lower()

                if (
                    "content unavailable" in body
                    or "no video available" in body
                ):
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

                driver.execute_script(
                    "arguments[0].pause();", video
                )

                src = video.get_attribute("src")

                if not src or src.endswith("missing.mp4"):
                    raise RuntimeError(
                        "Video source is missing or invalid"
                    )

                try:
                    driver.find_element(
                        By.CSS_SELECTOR,
                        'button[data-click="close"]'
                    ).click()
                except Exception:
                    pass

                clip_name = src.split("/")[-1].split("?")[0]

                if not clip_name.endswith(".mp4"):
                    clip_name = f"video_{i}.mp4"

                save_path = os.path.join(
                    download_dir, clip_name
                )

                print(f"Downloading: {clip_name}")

                base64_data = driver.execute_async_script(
                    js_download_script, src
                )

                if (
                    not base64_data
                    or base64_data.startswith("ERROR:")
                ):
                    raise RuntimeError(
                        f"Fetch failed: {base64_data}"
                    )

                video_bytes = base64.b64decode(
                    base64_data, validate=True
                )

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
                print(
                    f"Clip attempt {attempt} failed: {e}"
                )

                if attempt < max_retries:
                    time.sleep(2 * attempt)

                    try:
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
