"""
Entry point for the NBA daily-highlights agent.
"""
from datetime import date as date_cls

from nba_video_generator.nba_agent.config import FFMPEG_PATH
from nba_video_generator.nba_agent.orchestrator import run_for_date


def nba_agent(
        date: str | None = None, ffmpeg_path: str | None = None,
        threshold: bool = True, approve: bool = False
):
    if date is None:
        date = date_cls.today().isoformat()

    if ffmpeg_path is None:
        ffmpeg_path = FFMPEG_PATH

    run_for_date(date, ffmpeg_path, threshold, approve)
