"""Daily agent: find significant NBA performances and build highlight videos."""
import json
import os
import unicodedata
from collections import defaultdict
from datetime import date as date_cls

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

from .config import STATE_FILE, FFMPEG_PATH
from .team_map import abbr_for
from .scraper import get_boxscore_urls_for_date, parse_boxscore
from .significance import rule_based_candidates, ollama_judge
from .thumbnail import attach_headshot, make_thumbnail
from .team_logo import attach_logo

# Your existing video-generation pipeline (unchanged).
from nba_video_generator.beta_search import pipeline

# Where generated thumbnails are written.
THUMB_DIR = "thumbnails"


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _remove_accents(text: str) -> str:
    """Remove accents/diacritics from a string."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _player_name_parts(player_name: str) -> tuple[str, str]:
    """
    Split a player's name into (first_name, last_name).
    """
    parts = player_name.split()

    if not parts:
        return "", ""

    last_name = _remove_accents(parts[-1])
    first_name = _remove_accents(" ".join(parts[:-1]))

    if last_name in {"Sr.", "Jr.", "II", "III"} and len(parts) >= 2:
        last_name = _remove_accents(" ".join(parts[-2:]))
        first_name = _remove_accents(" ".join(parts[:-2]))

    return first_name, last_name


def _make_player_abbreviations(players) -> dict[tuple[str, str], str]:
    """
    Create display abbreviations for every player on a team.

    If multiple players share a last name, use the shortest first-name
    prefix that uniquely identifies each player.

    Example:
        Jaylen Williams -> Jay. Williams
        Jalen Williams  -> Jal. Williams

    The abbreviation is therefore determined from the complete roster,
    rather than from an individual player in isolation.
    """
    parsed = [
        _player_name_parts(player["PLAYER"])
        for player in players
        if player.get("PLAYER")
    ]

    # Group first names by normalized last name.
    by_last_name: dict[str, list[str]] = defaultdict(list)

    for first_name, last_name in parsed:
        by_last_name[last_name].append(first_name)

    abbreviations: dict[tuple[str, str], str] = {}

    for first_name, last_name in parsed:
        players_with_same_last = by_last_name[last_name]

        # No collision: last name alone is sufficient.
        if len(players_with_same_last) == 1:
            abbreviations[(first_name, last_name)] = last_name
            continue

        # Collision: find the shortest prefix of the first name
        # that uniquely identifies this player.
        for length in range(1, len(first_name) + 1):
            prefix = first_name[:length]

            matches = sum(
                other[:length] == prefix
                for other in players_with_same_last
            )

            if matches == 1:
                abbreviations[(first_name, last_name)] = (
                    f"{prefix}. {last_name}"
                )
                break
        else:
            # Extremely unlikely fallback if two players have
            # identical first and last names.
            abbreviations[(first_name, last_name)] = (
                f"{first_name}. {last_name}"
            )

    return abbreviations


def run_for_date(
    target_date: str | None = None,
    ffmpeg_path: str | None = None,
    threshold: bool = True,
    approve: bool = False,
) -> list[tuple[str, str, str, str]]:
    """
    Scan every box score for `target_date` (YYYY-MM-DD, defaults to today),
    find significant performances, and kick off video generation for each
    new one via your existing pipeline(). Also writes a thumbnail per
    queued performance to THUMB_DIR. Returns the jobs that were run.

    `ffmpeg_path` overrides config.FFMPEG_PATH for this run if given.
    """
    target_date = target_date or date_cls.today().isoformat()
    ffmpeg_path = ffmpeg_path or FFMPEG_PATH

    state = _load_state()
    state.setdefault(target_date, [])
    already_done = set(state[target_date])

    service = Service(log_output=os.devnull)
    options = webdriver.ChromeOptions()
    options.add_argument("--log-level=3")

    driver = webdriver.Chrome(service=service, options=options)
    driver.maximize_window()

    jobs: list[tuple[str, str, str, str]] = []
    stats = []
    thumb_jobs: list[tuple[str, str, dict]] = []
    already_done_list = []

    try:
        boxscore_urls = get_boxscore_urls_for_date(
            driver,
            target_date,
        )

        print(
            f"[{target_date}] "
            f"found {len(boxscore_urls)} box score(s)"
        )

        for url in boxscore_urls:
            teams = parse_boxscore(driver, url)

            if len(teams) != 2:
                print(
                    f"  ! skipping {url} "
                    f"(expected 2 teams, got {len(teams)})"
                )
                continue

            (team_a, players_a), (team_b, players_b) = list(
                teams.items()
            )

            game_label = f"{team_a} @ {team_b}"

            # Build the abbreviation map from the COMPLETE roster
            # of each team. This is necessary for cases such as:
            #
            #   Jaylen Williams -> Jay. Williams
            #   Jalen Williams  -> Jal. Williams
            #
            # rather than both becoming "J. Williams".
            abbreviations_a = _make_player_abbreviations(players_a)
            abbreviations_b = _make_player_abbreviations(players_b)

            candidates_a = rule_based_candidates(
                team_a,
                players_a,
                threshold,
            )

            candidates_b = rule_based_candidates(
                team_b,
                players_b,
                threshold,
            )

            picks = (
                ollama_judge(game_label, candidates_a + candidates_b)
            )

            print(
                f"  {game_label}: "
                f"{len(picks)} highlight-worthy performance(s)"
            )

            for pick in picks:
                player_name = pick["PLAYER"]

                first_name, last_name = _player_name_parts(
                    player_name
                )

                # Select the abbreviation map (and roster) belonging
                # to the player's team.
                if pick["TEAM"] == team_a:
                    abbreviations = abbreviations_a
                    roster = players_a

                elif pick["TEAM"] == team_b:
                    abbreviations = abbreviations_b
                    roster = players_b

                else:
                    print(
                        f"    ! could not identify team for "
                        f"{player_name}: {pick['TEAM']}"
                    )
                    continue

                player_abbreviation = abbreviations.get(
                    (first_name, last_name),
                    last_name,
                )

                # Full stat row (PTS, REB, IMAGE_URL, ...) for the thumbnail.
                stat_row = next(
                    (p for p in roster if p.get("PLAYER") == player_name),
                    {},
                )

                try:
                    team_abbr = abbr_for(pick["TEAM"])
                except KeyError as e:
                    print(f"    ! {e}")
                    continue

                # Use the COMPLETE player name in the state key.
                #
                # Do NOT use only:
                #     Williams|OKC
                #
                # because Jaylen Williams and Jalen Williams would
                # collide.
                normalized_player_name = _remove_accents(
                    player_name
                )

                key = (
                    f"{normalized_player_name}|"
                    f"{team_abbr}"
                )

                if key in already_done:
                    print(
                        f"    - skipping {player_name} "
                        f"(already processed today)"
                    )
                    continue

                # Download the headshot NOW, while the browser is still open
                # (plain HTTP requests to the NBA CDN tend to get blocked).
                attach_headshot(driver, stat_row)
                attach_logo(driver, stat_row, team_abbr)

                stat = (
                    f"{player_name} ({team_abbr}) — "
                    f"{pick['REASON']}"
                )

                if approve:
                    while True:
                        print(
                            f"    -> queuing video: {stat}"
                        )

                        choice = input(
                            "Approved Yes (y) / No (n): "
                        ).lower()

                        if choice in {"y", "n"}:
                            if choice == "y":
                                jobs.append(
                                    (
                                        (player_abbreviation, player_name),
                                        target_date,
                                        team_abbr,
                                    )
                                )

                                stats.append(stat)
                                thumb_jobs.append(
                                    (player_name, team_abbr, stat_row)
                                )
                                already_done.add(key)
                                already_done_list.append(key)

                            print()
                            break
                else:
                    print(
                        f"    -> queuing video: {stat}"
                    )
                    jobs.append(
                        (
                            (player_abbreviation, player_name),
                            target_date,
                            team_abbr,
                        )
                    )
                    stats.append(stat)
                    thumb_jobs.append(
                        (player_name, team_abbr, stat_row)
                    )
                    already_done.add(key)
                    already_done_list.append(key)

    finally:
        driver.close()

    if jobs:
        titles = pipeline(
            jobs,
            {
                "ffmpeg_path": ffmpeg_path,
            },
        )

        with open(
            "statlines.txt",
            "w",
            encoding="utf-8",
        ) as f:
            f.write("\n".join(stats))

        # One thumbnail per queued performance. A failure here should
        # never break the run, so each is guarded individually.
        for title, (name, abbr, row), key in zip(titles, thumb_jobs, already_done_list):
            # path = thumbnail_path(THUMB_DIR, target_date, name, abbr)
            path = os.path.join(THUMB_DIR, title + ".jpg")
            try:
                make_thumbnail(name, abbr, row, path)
                print(f"  thumbnail -> {path}")
            except Exception as e:
                print(f"  ! thumbnail failed for {name}: {e}")
            if not os.path.exists(title + ".mp4"):
                already_done.remove(key)
                
    state[target_date] = sorted(already_done)
    _save_state(state)

    return jobs
