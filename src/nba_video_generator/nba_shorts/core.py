"""High-level API: one game, or every game on a date."""
import re
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .browser import download_plays, open_browser, safe_name
from .config import Config
from .games import discover_games
from .ids import (
    event_url, game_type, get_game_id, parse_date, season_from_game_id
)
from .playbyplay import (
    MONTH_RE, get_game_date, get_game_title, get_pbp_browser
)
from .processed import is_processed, load_processed, mark_processed
from .scoring import Play, pick_plays
from .video import compile_clips, need_ffmpeg, to_vertical

from nba_video_generator.src.remove_duplicates import VideoDeduper


@dataclass
class GameResult:
    game_id: str
    title: str = ""
    plays: List[Play] = field(default_factory=list)
    clips: List[Path] = field(default_factory=list)
    compiled: Optional[Path] = None
    error: str = ""
    skipped: bool = False  # True when the game was already in processed_file


def _load_actions(driver, gid: str) -> list:
    return get_pbp_browser(driver, gid)


def process_game(driver, gid: str, cfg: Config, game_date: str = "",
                 title_override: str = "") -> GameResult:
    """Run the whole pipeline for one game using an existing Chrome driver."""
    print(
        f"\n=== Game {gid}  |  season {season_from_game_id(gid)}  |  "
        f"{game_type(gid)} ==="
    )

    if is_processed(cfg.processed_file, gid):
        print(f"Already in {cfg.processed_file}; skipping.")
        return GameResult(game_id=gid, skipped=True)

    actions = _load_actions(driver, gid)

    title = title_override or get_game_title(driver, gid)
    game_date = game_date or get_game_date(driver, gid)
    has_date = re.search(MONTH_RE + r"|\d{4}-\d{2}-\d{2}", title)
    parts = [title] + ([game_date] if game_date and not has_date else []) +\
        ["Top Plays"]
    video_title = " - ".join(parts)
    print(f"Video title: {video_title}")

    result = GameResult(game_id=gid, title=video_title)
    result.plays = pick_plays(actions, cfg.top, cfg.min_score, cfg.player)
    if not result.plays:
        result.error = ("No plays met the score threshold. "
                        "Try a lower min_score.")
        print(result.error)
        return result

    print(f"Picked {len(result.plays)} plays (game order):")
    for p in result.plays:
        print(f"  {p.score:5.1f}  Q{p.period} {p.clock}  [{p.event_id}] "
              f"{p.description}  ({', '.join(p.reasons)})")
    if cfg.dry_run:
        return result

    jobs = [(event_url(
        gid, p.event_id, p.description), p.description, p.event_id, p.score
        ) for p in result.plays]
    out_dir = Path(cfg.out) / gid
    if out_dir.exists():
        print(f"Removing existing output folder: {out_dir}")
        shutil.rmtree(out_dir)
    saved = download_plays(driver, out_dir, jobs, cfg.retries)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "title.txt").write_text(video_title, encoding="utf-8")
    print(f"{len(saved)}/{len(jobs)} clips downloaded to {out_dir}/")
    if not saved:
        result.error = ("Nothing downloaded. Preseason games often lack video;"
                        " try a regular-season game.")
        print(result.error)
        return result

    for path, _ in saved:
        p = Path(path)
        v = p.with_name(p.stem + "_9x16.mp4")
        print(f"Converting {p.name} -> 9:16")
        to_vertical(p, v, cfg.ffmpeg_path)
        os.remove(p)
        p = v
        result.clips.append(p)

    dest_dir = Path(cfg.compiled_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / f"{safe_name(video_title, 80)}_raw.mp4"
    print("Compiling ...")
    compile_clips(result.clips, dst, cfg.ffmpeg_path, video_title)
    dst_final = dest_dir / f"{safe_name(video_title, 80)}.mp4"
    dedupe = VideoDeduper(dst, cfg.ffmpeg_path)
    dedupe.run(dst_final)
    if os.path.exists(dst):
        os.replace(dst, dst_final)
    print(f"Compilation: {dst_final}")
    result.compiled = dst_final

    # Only a finished video counts as processed.
    mark_processed(cfg.processed_file, gid, video_title, dst_final)
    print(f"Recorded {gid} in {cfg.processed_file}")
    shutil.rmtree(out_dir)

    return result


def _check_ffmpeg(cfg: Config):
    if not cfg.dry_run:
        need_ffmpeg(cfg.ffmpeg_path)


def make_shorts(
        game: str, cfg: Optional[Config] = None, driver=None
) -> GameResult:
    """Make shorts for one game (10-digit ID or nba.com URL).

    Pass `driver` to reuse an open Chrome; otherwise one is opened and
    closed for you. A game already listed in cfg.processed_file is skipped.
    """
    cfg = cfg or Config()
    gid = get_game_id(game)
    if is_processed(cfg.processed_file, gid):
        return process_game(None, gid, cfg)
    _check_ffmpeg(cfg)
    if driver is not None:
        return process_game(driver, gid, cfg, cfg.title_date, cfg.title)
    with open_browser(cfg.headless) as d:
        return process_game(d, gid, cfg, cfg.title_date, cfg.title)


def list_games(date, driver=None, headless: bool = False) -> List[str]:
    """Game IDs listed on nba.com/games for a date
    (str like '2026-10-05' or a date)."""
    d = parse_date(date) if isinstance(date, str) else date
    if driver is not None:
        return discover_games(driver, d)
    with open_browser(headless) as drv:
        return discover_games(drv, d)


def make_shorts_for_date(
        date: str = None,
        ffmpeg_path: str = (
            r"C:\Users\ronen\Documents\Projects\nba_video_generator\src"
            r"\nba_video_generator\ffmpeg-9.0.2-essentials_build\bin\ffmpeg"
            r".exe"
        )
) -> List[GameResult]:
    """Make shorts for every game on a day, using nba.com/games to find them.

    Games already in cfg.processed_file are skipped
    (and don't count toward max_games),
    so max_games means "make at most N new videos".
    """
    cfg = Config(ffmpeg_path=ffmpeg_path)
    if date is None:
        date = "today"
    d = parse_date(date) if isinstance(date, str) else date
    _check_ffmpeg(cfg)
    label = cfg.title_date or f"{d.strftime('%b')} {d.day}, {d.year}"

    def run(drv) -> List[GameResult]:
        games = discover_games(drv, d)
        if not games:
            raise LookupError(f"No games found on nba.com/games for {d}.")
        print(f"Found {len(games)} game(s) for {d}: {', '.join(games)}")

        results = []
        done = load_processed(cfg.processed_file)
        for gid in [g for g in games if g in done]:
            print(f"Skipping {gid}: already in {cfg.processed_file}")
            results.append(GameResult(game_id=gid, skipped=True))
        games = [g for g in games if g not in done]

        for n, gid in enumerate(games, 1):
            print(f"\n##### Game {n}/{len(games)} #####")
            try:
                results.append(
                    process_game(drv, gid, cfg, label,
                                 cfg.title if len(games) == 1 else ""))
            except Exception as e:
                print(f"Game {gid} failed: {e}")
                results.append(GameResult(game_id=gid, error=str(e)))
            time.sleep(2)
        return results

    with open_browser(cfg.headless) as drv:
        return run(drv)


def find_top_plays(
        game: str, cfg: Optional[Config] = None, driver=None
) -> List[Play]:
    """Pick the plays only (no clip downloads)."""
    cfg = cfg or Config()
    gid = get_game_id(game)

    def run(drv):
        return pick_plays(
            _load_actions(drv, gid), cfg.top, cfg.min_score, cfg.player
        )

    if driver is not None:
        return run(driver)
    with open_browser(cfg.headless) as drv:
        return run(drv)
