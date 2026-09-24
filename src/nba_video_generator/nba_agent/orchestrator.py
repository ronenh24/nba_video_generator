"""Daily agent: find significant NBA performances and build highlight videos."""
import json
import os
from datetime import date as date_cls

from selenium import webdriver

from .config import STATE_FILE, FFMPEG_PATH
from .team_map import abbr_for
from .scraper import get_boxscore_urls_for_date, parse_boxscore
from .significance import rule_based_candidates, ollama_judge

# Your existing video-generation pipeline (unchanged).
from nba_video_generator.beta_search import pipeline


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def run_for_date(
    target_date: str | None = None, ffmpeg_path: str | None = None, threshold: bool = True
) -> list[tuple[str, str, str, str]]:
    """
    Scan every box score for `target_date` (YYYY-MM-DD, defaults to today),
    find significant performances, and kick off video generation for each
    new one via your existing pipeline(). Returns the jobs that were run.

    `ffmpeg_path` overrides config.FFMPEG_PATH for this run if given.
    """
    target_date = target_date or date_cls.today().isoformat()
    ffmpeg_path = ffmpeg_path or FFMPEG_PATH
    state = _load_state()
    state.setdefault(target_date, [])
    already_done = set(state[target_date])

    driver = webdriver.Chrome()
    driver.maximize_window()

    jobs: list[tuple[str, str, str, str]] = []
    stats = []

    try:
        boxscore_urls = get_boxscore_urls_for_date(driver, target_date)
        print(f"[{target_date}] found {len(boxscore_urls)} box score(s)")

        for url in boxscore_urls:
            teams = parse_boxscore(driver, url)
            if len(teams) != 2:
                print(f"  ! skipping {url} (expected 2 teams, got {len(teams)})")
                continue

            (team_a, players_a), (team_b, players_b) = list(teams.items())
            game_label = f"{team_a} @ {team_b}"

            candidates = rule_based_candidates(team_a, players_a, threshold) + \
                rule_based_candidates(team_b, players_b, threshold)
            picks = ollama_judge(game_label, candidates)

            print(f"  {game_label}: {len(picks)} highlight-worthy performance(s)")

            for pick in picks:
                last_name = pick["PLAYER"].split()[-1]
                try:
                    team_abbr = abbr_for(pick["TEAM"])
                except KeyError as e:
                    print(f"    ! {e}")
                    continue

                key = f"{last_name}|{team_abbr}"
                if key in already_done:
                    print(f"    - skipping {pick['PLAYER']} (already processed today)")
                    continue

                stat = f"{pick['PLAYER']} ({team_abbr}) — {pick['REASON']}"
                print(f"    -> queuing video: {stat}")
                jobs.append((last_name, target_date, target_date, team_abbr))
                stats.append(stat)
                already_done.add(key)
    finally:
        driver.close()

    if jobs:
        pipeline(jobs, {"ffmpeg_path": ffmpeg_path})
        for stat in stats:
            print(stat)

    state[target_date] = sorted(already_done)
    _save_state(state)
    return jobs
