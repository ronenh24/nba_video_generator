"""
Makes video for specified players and date(s).
"""

# Last Name
# Home Team
# Team Abbreviation
import os
import subprocess
from datetime import datetime, timedelta
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from .get_pbp_beta import get_pbp
from .get_plays_beta import get_plays
from .download_plays_beta import download_plays
from .write_plays_beta import write_plays
from nba_video_generator.processed_performances import (
    STATE_FILE,
    load_processed_performances,
    performance_key,
    save_processed_performances,
)


BASE_URL = "https://www.nba.com/games?date="
FFMPEG_PATH = (
    r"C:\Users\ronen\Documents\Projects\nba_video_generator\src"
    r"\nba_video_generator\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe"
)


def search(driver: webdriver, last_name: str, date_start: str, date_end: str,
           team: str, ffmpeg_path: str = FFMPEG_PATH,
           preset: str = "veryfast", full_name: str | None = None,
           output_dir: str = "."):
    """Makes video for player and date(s)."""
    if date_end is None:
        date_end = date_start

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    time_secs = 0
    desc_txt = None
    title = None
    generated_title = None
    titles = []
    generated_dates = []
    processed_state = load_processed_performances(STATE_FILE)
    state_key = performance_key(full_name or last_name, team)
    base_name = os.path.join(output_dir, last_name.lower())
    file_list_path = os.path.join(output_dir, "file_list.txt")
    current_date = datetime.strptime(date_start, "%Y-%m-%d")
    end_date = datetime.strptime(date_end, "%Y-%m-%d")
    file_list = None
    file_list_created = False

    try:
        if date_start != date_end:
            file_list = open(file_list_path, "w", encoding="utf-8")
            file_list_created = True
            desc_txt = open(
                os.path.join(
                    output_dir,
                    last_name + " " + date_start + " " + date_end +
                    " description.txt",
                ),
                "w",
                encoding="utf-8",
            )
        while current_date <= end_date:
            date = current_date.strftime("%Y-%m-%d")
            if state_key in processed_state.get(date, []):
                print(
                    f"Skipping {full_name or last_name} on {date}: "
                    "already processed"
                )
                current_date += timedelta(days=1)
                continue

            data_is_home_team, pbp_url = get_pbp(driver, BASE_URL, date, team)

            if pbp_url is not None:
                title, result = get_plays(
                    driver, pbp_url, last_name, data_is_home_team
                )

                if full_name is not None:
                    title = full_name + title
                else:
                    title = last_name + title

                if len(result) > 0:
                    try:
                        shutil.rmtree(base_name)
                    except Exception:
                        pass

                    os.makedirs(base_name)

                    player_urls = download_plays(driver, base_name, result)
                    if not player_urls:
                        print(
                            f"No playable clips found for {last_name} on "
                            f"{date}"
                        )
                    else:
                        time_secs, desc_txt = write_plays(
                            title,
                            base_name,
                            player_urls,
                            ffmpeg_path,
                            preset,
                            time_secs,
                            desc_txt,
                            output_dir,
                        )

                        title_path = os.path.join(
                            output_dir, title + ".mp4"
                        )
                        if (
                            not os.path.isfile(title_path)
                            or os.path.getsize(title_path) == 0
                        ):
                            raise RuntimeError(
                                "Video was not created successfully: "
                                f"{title_path}"
                            )

                        if date_start != date_end:
                            file_list.write(f"file '{title_path}'\n")
                            titles.append(title_path)
                            generated_dates.append(date)
                        else:
                            processed_state.setdefault(date, [])
                            if state_key not in processed_state[date]:
                                processed_state[date].append(state_key)
                                processed_state[date].sort()
                            save_processed_performances(
                                processed_state, STATE_FILE
                            )
                            generated_title = title

            current_date += timedelta(days=1)

        if date_start != date_end:
            file_list.close()
            file_list = None
            if desc_txt is not None:
                desc_txt.close()
                desc_txt = None

            if not titles:
                print(
                    f"No new videos generated for {last_name} from "
                    f"{date_start} to {date_end}"
                )
                return None

            output_path = os.path.join(
                output_dir,
                last_name + " " + date_start + " " + date_end + " Full Play.mp4",
            )

            if os.path.exists(output_path):
                os.remove(output_path)

            subprocess.run([
                ffmpeg_path, "-f", "concat", "-safe", "0",
                "-i", file_list_path, "-c", "copy", output_path
            ], check=True)
            if (
                not os.path.isfile(output_path)
                or os.path.getsize(output_path) == 0
            ):
                raise RuntimeError(
                    f"Combined video was not created successfully: "
                    f"{output_path}"
                )

            for date in generated_dates:
                processed_state.setdefault(date, [])
                if state_key not in processed_state[date]:
                    processed_state[date].append(state_key)
                    processed_state[date].sort()
            save_processed_performances(processed_state, STATE_FILE)

            for title_path in titles:
                os.remove(title_path)

            return last_name + " " + date_start + " " + date_end

        return generated_title
    finally:
        if file_list is not None:
            file_list.close()
        if desc_txt is not None:
            desc_txt.close()
        if file_list_created and os.path.exists(file_list_path):
            os.remove(file_list_path)
        shutil.rmtree(base_name, ignore_errors=True)


def pipeline(
        name_date_team: list[tuple[str | tuple[str, str], str, str]] |
        list[tuple[str | tuple[str, str], str, str, str]],
        params: dict | None = None,
):
    """Makes videos for players and dates(s)."""
    params = dict(params or {})

    for i, row in enumerate(name_date_team):
        if len(row) == 3:
            name_date_team[i] = (row[0], row[1], row[1], row[2])

    titles = []

    for name, date_start, date_end, team in name_date_team:
        full_player_name = (
            name[1] if isinstance(name, tuple)
            else params.get("full_name") or name
        )
        state_key = performance_key(full_player_name, team)
        processed_state = load_processed_performances(STATE_FILE)
        first_date = datetime.strptime(date_start, "%Y-%m-%d")
        last_date = datetime.strptime(date_end, "%Y-%m-%d")
        requested_dates = []
        current_date = first_date
        while current_date <= last_date:
            requested_dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

        if requested_dates and all(
            state_key in processed_state.get(date, [])
            for date in requested_dates
        ):
            print(
                f"Skipping {full_player_name} on "
                f"{date_start} through {date_end}: already processed"
            )
            continue

        service = Service(log_output=os.devnull)
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--log-level=3")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            (
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            )
        )
        driver = webdriver.Chrome(service=service, options=options)
        # driver.maximize_window()
        # driver.implicitly_wait(3)
        if isinstance(name, str):
            params["last_name"] = name
            params.pop("full_name", None)
        else:
            params["last_name"] = name[0]
            if params["last_name"] == "Yang":
                params["last_name"] = "Hansen"
            params["full_name"] = name[1]
        params["date_start"] = date_start
        params["date_end"] = date_end
        params["team"] = team
        params["driver"] = driver
        try:
            title = search(**params)
            if title is not None:
                titles.append(title)
        except Exception as e:
            print(
                f"Failed to generate video for {name} on {date_start}: {e}"
            )
        finally:
            driver.quit()

    return titles
