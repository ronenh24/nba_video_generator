"""Settings shared by the API and the command line."""
from dataclasses import dataclass


@dataclass
class Config:
    top: int = 4                  # plays per game
    min_score: float = 3.0        # minimum play score
    player: str = ""              # only plays whose description contains this text
    out: str = "."                # root folder for individual clips
    compiled_dir: str = "."       # where compiled videos are saved
    headless: bool = True         # headless Chrome (the NBA player often refuses it)
    retries: int = 3              # download attempts per clip
    dry_run: bool = False         # pick plays only, download nothing
    title: str = ""               # override the video title (single game)
    title_date: str = ""          # override the date used in the title
    ffmpeg_path: str = ""
    processed_file: str = "processed_shorts.json"
