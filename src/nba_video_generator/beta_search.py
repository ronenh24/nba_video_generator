# Last Name
# Home Team
# Team Abbreviation
import os
import subprocess
import time
from textwrap import fill
from typing import Literal
from datetime import datetime, timedelta
from moviepy import \
    TextClip, VideoFileClip, CompositeVideoClip, concatenate_videoclips
from selenium import webdriver
from selenium.webdriver.common.by import By


base_url = "https://www.nba.com/games?date="
boxscore_tag = "//a[@data-text='BOX SCORE']"
time_tag = ".//span[starts-with(@class, 'GamePlayByPlayRow_clockElement')]"
desc_tag = ".//span[starts-with(@class, 'GamePlayByPlayRow_desc')]"
video_tag = "//h2[starts-with(@class, 'VideoPlayer_videoTitle')]"


def search(driver: webdriver, last_name: str, date: str, team: str,
           fps: int = 30, preset: str = "ultrafast", include_caption: bool = True):
    driver.get(base_url + date)

    body = driver.find_element(By.TAG_NAME, "body").text.lower()

    while "content unavailable" in body:
        driver.refresh()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

    box_score_url = ""

    game_urls = driver.find_elements(By.XPATH, boxscore_tag)

    for game_url in game_urls:
        game_url = game_url.get_attribute("href")
        if team in game_url:
            box_score_url = game_url

    if box_score_url == "":
        return {}

    home_away = box_score_url.split("vs")[1]

    if team in home_away:
        data_is_home_team = "true"
    else:
        data_is_home_team = "false"

    pbp_url = box_score_url.rsplit("/", 1)[0] + "/play-by-play"

    driver.get(pbp_url)

    title = last_name + " " + driver.title.rstrip(" Play-by-Play | NBA.com") + " Full Play"

    body = driver.find_element(By.TAG_NAME, "body").text.lower()

    while "content unavailable" in body:
        driver.refresh()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

    tabs = driver.find_elements(
        By.CSS_SELECTOR,
        "nav.GamePlayByPlay_periods__RYwbX button"
    )

    result = []
    quarter = 1

    for tab in tabs[:-1]:
        driver.execute_script("arguments[0].click();", tab)

        play_by_play = driver.find_element(By.ID, "playByPlayContainer")
        rows = play_by_play.find_elements(By.TAG_NAME, "article")

        for i, row in enumerate(rows):
            if row.get_attribute("data-is-home-team") == data_is_home_team and last_name in row.text:
                try:
                    desc_raw = row.find_element(By.XPATH, desc_tag).text
                    desc = desc_raw.lower()
                    play_time = row.find_element(By.XPATH, time_tag).text
                    if play_time.startswith("0"):
                        play_time = play_time[1:]
                    play_time = int(play_time.split(":")[0]) * 60 + int(play_time.split(":")[1])
                    link = row.find_element(By.TAG_NAME, "a")
                    video_url = link.get_attribute("href")
                    if "free throw 1 of" in desc:
                        try:
                            foul_link, foul_desc = _find_foul_url(rows, i, play_time)
                            result.append(
                                (
                                    foul_link,
                                    foul_desc,
                                    quarter,
                                    play_time,
                                )
                            )
                        except Exception:
                            pass
                    result.append(
                        (
                            video_url,
                            desc_raw,
                            quarter,
                            play_time
                        )
                    )
                except Exception:
                    pass
        quarter += 1

    result = combine_events(result)

    player_urls = []
    for video_url, desc_raw, _, _ in result:
        driver.get(video_url)

        body = driver.find_element(By.TAG_NAME, "body").text.lower()

        while "content unavailable" in body or \
                "no video available" in body:
            driver.refresh()
            body = driver.find_element(By.TAG_NAME, "body").text.lower()

        video = driver.find_element(By.CLASS_NAME, 'vjs-tech')
        video_url = video.get_attribute('src')
        if not video_url.endswith("missing.mp4"):
            player_urls.append((video_url, desc_raw))

    base_name = last_name.lower()

    try:
        os.makedirs(base_name)
    except Exception:
        pass

    desc_txt = open(base_name.lower() + "_description.txt", "w+")
    time_secs = 0

    for i, (event_url, desc) in enumerate(player_urls):
        desc_txt.write(time.strftime('%H:%M:%S', time.gmtime(time_secs)) + " - " + desc + "\n")
        video_clip = VideoFileClip(event_url)
        if include_caption:
            desc_clip = TextClip(
                text=desc, font_size=18, color="white",
                size=(1280, None)
            ).with_position("top").with_duration(video_clip.duration)
            clip = CompositeVideoClip([video_clip, desc_clip], use_bgclip=True)
            clip.audio = video_clip.audio
        else:
            clip = video_clip
        time_secs += clip.duration
        clip.write_videofile(
            base_name.lower() + "/" + base_name.lower() + "_" + date.replace("-", "") + "_play" +
            str(i) + ".mp4", fps=fps, preset=preset, threads=3
        )

    desc_txt.close()

    ffmpeg_path = r"C:\Users\ronen\Documents\Projects\nba_video_generator\src\nba_video_generator\ffmpeg-2025-10-21-git-535d4047d3-essentials_build\bin\ffmpeg.exe"

    files = [
        os.path.join(os.path.abspath(base_name), f)
        for f in os.listdir(base_name)
        if f.lower().endswith(".mp4")
    ]

    files.sort(key=os.path.getctime)

    list_path = os.path.join(base_name, "file_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for file_path in files:
            safe_path = file_path.replace("\\", "/")
            f.write(f"file '{safe_path}'\n")

    output_path = title + ".mp4"

    if os.path.exists(output_path):
        os.remove(output_path)

    subprocess.run([
        ffmpeg_path, "-f", "concat", "-safe", "0",
        "-i", list_path, "-c", "copy", output_path
    ])


def _find_foul_url(rows, i, play_time):
    for j in range(i - 1, -1, -1):
        try:
            t = rows[j].find_element(By.XPATH, time_tag).text
            if t.startswith("0"):
                t = t[1:]
            t = int(t.split(":")[0]) * 60 + int(t.split(":")[1])
        except:
            continue

        if t != play_time:
            break

        desc = rows[j].find_element(By.XPATH, desc_tag).text.lower()
        if "foul" in desc:
            link = rows[j].find_element(By.TAG_NAME, "a")
            return link.get_attribute("href"), rows[j].find_element(By.XPATH, desc_tag).text

    return None


def combine_events(events, max_gap=5):
    combined = []
    current = None

    for url, desc, quarter, time in events:
        desc_l = desc.lower()

        is_free_throw = "free throw" in desc_l
        is_foul = "foul" in desc_l

        event = {
            "url": url,
            "desc": desc,
            "quarter": quarter,
            "time": time,
        }

        if is_free_throw:
            if current:
                combined.append((
                    current["url"],
                    current["desc"],
                    current["quarter"],
                    current["time"],
                ))
                current = None

            combined.append((url, desc, quarter, time))
            continue

        if current is None:
            current = event
            continue

        same_quarter = quarter == current["quarter"]
        time_diff = abs(current["time"] - time)

        can_merge = (
            same_quarter
            and time_diff <= max_gap
            and "foul" not in current["desc"].lower()
        )

        if can_merge:
            current["desc"] = f'{current["desc"]}, {desc}'
            current["url"] = url
            current["time"] = max(current["time"], time) 
        else:
            combined.append((
                current["url"],
                current["desc"],
                current["quarter"],
                current["time"],
            ))
            current = event

    if current:
        combined.append((
            current["url"],
            current["desc"],
            current["quarter"],
            current["time"],
        ))

    return combined


def pipeline(name_date_team: list[tuple[str, str, str]], params: dict = {}):
    driver = webdriver.Chrome()
    driver.implicitly_wait(5)

    for last_name, date, team in name_date_team:
        params["last_name"] = last_name
        params["date"] = date
        params["team"] = team
        params["driver"] = driver
        search(**params)

    driver.close()

# pipeline(
#     [
#        ("Booker", "2026-02-19", "phx"),
#     ]
# )

