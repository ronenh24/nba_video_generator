"""nba_shorts - find highlight-worthy NBA plays, download the clips,
                make Shorts.

    from nba_shorts import Config, make_shorts, make_shorts_for_date

    make_shorts("0012600055", Config(top=6, vertical=True, compilation=True))
    make_shorts_for_date("yesterday", Config(vertical=True, compilation=True))
"""
from .browser import download_plays, make_driver, open_browser
from .config import Config
from .core import (GameResult, find_top_plays, list_games, make_shorts,
                   make_shorts_for_date, process_game)
from .games import discover_games
from .ids import (
    event_url, game_type, get_game_id, parse_date, season_from_game_id
)
from .scoring import Play, pick_plays, score_play
from .video import compile_clips, to_vertical

__version__ = "0.1.0"

__all__ = [
    "Config", "GameResult", "Play",
    "make_shorts", "make_shorts_for_date", "find_top_plays", "list_games",
    "process_game", "pick_plays", "score_play", "discover_games",
    "download_plays", "make_driver", "open_browser", "to_vertical",
    "compile_clips", "get_game_id", "parse_date", "season_from_game_id",
    "game_type", "event_url",
]
