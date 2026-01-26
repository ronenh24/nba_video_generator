from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


table_tag = '//table[starts-with(@class, "Crom_table")]'
icon_tag = './/td[starts-with(@class, "Crom_sticky")]'
desc_tag = ".//span[starts-with(@class, 'GamePlayByPlayRow_desc')]"
time_tag = ".//span[starts-with(@class, 'GamePlayByPlayRow_clockElement')]"
video_tag = "//h2[starts-with(@class, 'VideoPlayer_videoTitle')]"


def get_videos(driver: webdriver, url: str, fg: bool = True) -> \
        dict[str, list[tuple[str, str]]]:
    """
    From video url, returns event description as key and
    url and quarter as values.
    """
    video_urls = {}

    driver.get(url)

    body = driver.find_element(By.TAG_NAME, "body").text.lower()
    while "content unavailable" in body or "no video available" in body or "no data available" in body:
        time.sleep(30)
        driver.refresh()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

    wait = WebDriverWait(driver, 120)
    table = wait.until(EC.visibility_of_element_located((By.XPATH, table_tag)))
    # table = driver.find_element(By.XPATH, table_tag)
    rows = table.find_elements(By.TAG_NAME, "tr")

    rows = rows[1:]

    for i, row in enumerate(rows):
        try:
            icon = row.find_element(By.XPATH, icon_tag)

            driver.execute_script("arguments[0].click();", icon)

            video = driver.find_element(By.CLASS_NAME, 'vjs-tech')
            video_url = video.get_attribute('src')
            if not video_url.endswith("missing.mp4"):
                description = driver.find_element(
                    By.XPATH, video_tag
                ).text.lower()
                if fg:
                    period = row.find_element(By.XPATH, "./td[10]").text
                else:
                    period = row.find_element(By.XPATH, "./td[7]").text
                if description not in video_urls:
                    video_urls[description] = []
                video_urls[description].append((video_url, period))

                print(f"[{i+1}] Video URL: {video_url}")
        except Exception:
            pass

    return video_urls


def sort_plays(driver: webdriver, pbp: str, video_urls: dict[str, list[tuple[str, str]]]) -> \
        list[tuple[str, str, str]]:
    """
    Sorts the plays by order of description.

    Returns url, quarter, and time.
    """
    pbp = pbp.rsplit("/", 1)[0] + "/play-by-play?period=All"

    driver.get(pbp)

    body = driver.find_element(By.TAG_NAME, "body").text.lower()

    while "content unavailable" in body:
        driver.refresh()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

    play_by_play = driver.find_element(By.ID, "playByPlayContainer")
    rows = play_by_play.find_elements(By.TAG_NAME, "article")

    result = []

    for row in rows:
        desc_raw = row.find_element(By.XPATH, desc_tag).text
        desc = desc_raw.lower()

        if desc in video_urls:
            play_time = row.find_element(By.XPATH, time_tag).text
            if play_time.startswith("0"):
                play_time = play_time[1:]
            play_time = int(play_time.split(":")[0]) * 60 + int(play_time.split(":")[1])

            video_url, quarter = video_urls[desc][0]
            if len(result) > 0 and "free throw" not in desc:
                _, prev_desc, prev_quarter, prev_time = result[-1]
                if prev_quarter == quarter and prev_time - play_time <= 5 and \
                        "foul" not in prev_desc and "free throw" not in prev_desc:
                    result.pop(-1)
                    result.append(
                        (
                            video_url,
                            prev_desc + ", " + desc_raw,
                            quarter,
                            play_time
                        )
                    )
                else:
                    result.append(
                    (
                        video_url,
                        desc_raw,
                        quarter,
                        play_time,
                    )
                )
            else:
                result.append(
                    (
                        video_url,
                        desc_raw,
                        quarter,
                        play_time,
                    )
                )

            video_urls[desc].pop(0)
            if not video_urls[desc]:
                del video_urls[desc]

            if not video_urls:
                break

    return result


def get_ft_or_foul_videos(driver: webdriver, urls: list[tuple[str, str]]) -> \
        dict[str, list[tuple[str, str]]]:
    """
    From free throw or foul url, returns description as key and
    url and quarter as values.
    """
    video_urls = {}

    for i, (url, quarter) in enumerate(urls):
        try:
            driver.get(url)

            body = driver.find_element(By.TAG_NAME, "body").text.lower()

            while "content unavailable" in body or \
                    "no video available" in body:
                driver.refresh()
                body = driver.find_element(By.TAG_NAME, "body").text.lower()

            video = driver.find_element(By.CLASS_NAME, 'vjs-tech')
            video_url = video.get_attribute('src')
            if not video_url.endswith("missing.mp4"):
                description = driver.find_element(
                    By.XPATH, video_tag
                ).text.lower()
                if description not in video_urls:
                    video_urls[description] = []
                video_urls[description].append((video_url, quarter))

                print(f"[{i+1}] Video URL: {video_url}")
        except Exception:
            pass

    return video_urls
