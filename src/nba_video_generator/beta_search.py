# Last Name
# Home Team
# Team Abbreviation
import os
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


def search(driver: webdriver, last_name: str, date_start: str, date_end: str, team: str, ffmpeg_path: str, 
           fps: int = 60, preset: str = "ultrafast", include_caption: bool = True):
    if date_end is None:
        date_end = date_start

    current_date = datetime.strptime(date_start, "%Y-%m-%d")
    end_date = datetime.strptime(date_end, "%Y-%m-%d")

    while current_date <= end_date:
        date = current_date.strftime("%Y-%m-%d")
        data_is_home_team, pbp_url = get_pbp(driver, base_url, date, team)

        title, result = get_plays(driver, pbp_url, last_name, data_is_home_team)

        base_name = last_name.lower()

        try:
            shutil.rmtree(base_name)
        except Exception:
            pass
        os.makedirs(base_name)

        player_urls = download_plays(driver, base_name, result)

        write_plays(title, base_name, date, player_urls, ffmpeg_path, include_caption, fps, preset)

        current_date += timedelta(days=1)


def pipeline(name_date_team: list[tuple[str, str, str]] | list[tuple[str, str, str, str]],
             params: dict = {}):

    if len(name_date_team[0]) == 3:
        name_date_team = [
            (last_name, date_start, date_start, team) 
            for last_name, date_start, team in name_date_team
        ]

    for last_name, date_start, date_end, team in name_date_team:
        driver = webdriver.Chrome()
        driver.implicitly_wait(10)
        params["last_name"] = last_name
        params["date_start"] = date_start
        params["date_end"] = date_end
        params["team"] = team
        params["driver"] = driver
        search(**params)
        driver.close()

