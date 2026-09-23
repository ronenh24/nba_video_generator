"""Entry point for the NBA daily-highlights agent.

Usage:
    python run_agent.py                                  # process today's games
    python run_agent.py --date 2026-09-21                 # process a specific date
    python run_agent.py --ffmpeg-path C:\\path\\ffmpeg.exe  # override ffmpeg location
    python run_agent.py --loop --at 04:00                 # run once a day, forever
"""
import argparse
from datetime import date as date_cls

from nba_video_generator.nba_agent.config import FFMPEG_PATH
from nba_video_generator.nba_agent.orchestrator import run_for_date


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="YYYY-MM-DD, defaults to today")
    parser.add_argument(
        "--ffmpeg-path",
        dest="ffmpeg_path",
        default=FFMPEG_PATH,
        help=f"path to ffmpeg executable (default: {FFMPEG_PATH})",
    )
    parser.add_argument("--loop", action="store_true", help="run once a day forever")
    parser.add_argument(
        "--at", default="04:00", help="daily run time (24h local, used with --loop)"
    )
    args = parser.parse_args()

    if not args.loop:
        run_for_date(args.date, ffmpeg_path=args.ffmpeg_path)
        return

    import time
    import schedule

    schedule.every().day.at(args.at).do(run_for_date, ffmpeg_path=args.ffmpeg_path)
    print(f"Agent scheduled daily at {args.at}. Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)

def nba_agent(date: str | None = None, ffmpeg_path: str | None = None):
    if date is None:
        date = date_cls.today().isoformat()

    if ffmpeg_path is None:
        ffmpeg_path = FFMPEG_PATH

    run_for_date(date, ffmpeg_path)

if __name__ == "__main__":
    main()
