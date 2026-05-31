# Last Name
# Home Team
# Team Abbreviation
import os
import subprocess
import time
from datetime import datetime, timedelta
import shutil
from moviepy import \
    TextClip, VideoFileClip, CompositeVideoClip, concatenate_videoclips
from selenium import webdriver
from nba_video_generator.src.get_pbp_beta import get_pbp
from nba_video_generator.src.get_plays_beta import get_plays
from nba_video_generator.src.download_plays_beta import download_plays
from nba_video_generator.src.write_plays_beta import write_plays


base_url = "https://www.nba.com/games?date="


def search(driver: webdriver, last_name: str, date_start: str, date_end: str, team: str,
           ffmpeg_path: str, preset: str = "ultrafast"):
    if date_end is None:
        date_end = date_start

    current_date = datetime.strptime(date_start, "%Y-%m-%d")
    end_date = datetime.strptime(date_end, "%Y-%m-%d")

    if date_start != date_end:
        f = open("file_list.txt", "w", encoding="utf-8")

    while current_date <= end_date:
        date = current_date.strftime("%Y-%m-%d")
        data_is_home_team, pbp_url = get_pbp(driver, base_url, date, team)
    
        if pbp_url is not None:
            title, result = get_plays(driver, pbp_url, last_name, data_is_home_team)

            if len(result) > 0:
                base_name = last_name.lower()

                try:
                    shutil.rmtree(base_name)
                except Exception:
                    pass
                os.makedirs(base_name)

                player_urls = download_plays(driver, base_name, result)

                write_plays(title, base_name, date, player_urls, ffmpeg_path, preset)

                if date_start != date_end:
                    f.write(f"file '{os.path.abspath(title + '.mp4')}'\n")

        current_date += timedelta(days=1)

    if date_start != date_end:
        f.close()

        output_path = last_name + " " + date_start + " " + date_end + " Full Play.mp4"

        if os.path.exists(output_path):
            os.remove(output_path)

        subprocess.run([
            ffmpeg_path, "-f", "concat", "-safe", "0",
            "-i", "file_list.txt", "-c", "copy", output_path
        ])


def pipeline(name_date_team: list[tuple[str, str, str]] | list[tuple[str, str, str, str]],
             params: dict = {}):

    for i, row in enumerate(name_date_team):
        if len(row) == 3:
            name_date_team[i] = (row[0], row[1], row[1], row[2])

    for last_name, date_start, date_end, team in name_date_team:
        driver = webdriver.Chrome()
        driver.maximize_window()
        # driver.implicitly_wait(3)
        params["last_name"] = last_name
        params["date_start"] = date_start
        params["date_end"] = date_end
        params["team"] = team
        params["driver"] = driver
        search(**params)
        driver.close()

