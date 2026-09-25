"""Configuration for the NBA daily-highlights agent."""
import os

# --- Ollama settings ---
# Requires a local Ollama server (https://ollama.com) with a model pulled,
# e.g.:  ollama pull gemma3:4b
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

# --- Paths ---
# Tracks which (player, team) pairs already had a video made for a given
# date, so re-running the agent doesn't regenerate the same clip.
STATE_FILE = os.environ.get("NBA_AGENT_STATE", "processed_performances.json")

# Passed straight through to your existing pipeline()/write_plays() code.
FFMPEG_PATH = os.environ.get(
    "FFMPEG_PATH",
    r"C:\Users\ronen\Documents\Projects\nba_video_generator\src\nba_video_generator"
    r"\ffmpeg-2025-10-21-git-535d4047d3-essentials_build\bin\ffmpeg.exe",
)

# --- Rule-based "worth a look" thresholds ---
# Any player who clears ONE of these gets sent to the LLM for a final
# highlight-worthy/not judgment call. Keeps the LLM prompt small and keeps
# it from hallucinating candidates out of thin air.
THRESHOLDS = {
    "PTS": 20,
    "REB": 10,
    "AST": 5,
    "STL": 2,
    "BLK": 2,
    "3PM": 5,
}
TRIPLE_DOUBLE_CATS = ["PTS", "REB", "AST", "STL", "BLK"]
TRIPLE_DOUBLE_MIN = 10  # double-digit in 3+ of the categories above

BASE_GAMES_URL = "https://www.nba.com/games?date={date}"

# --- Scraper retry settings ---
# nba.com occasionally serves a page that loads but never finishes
# hydrating (empty game list / no table). These control how the scraper
# retries — reloading and backing off — before giving up on a page.
SCRAPE_MAX_ATTEMPTS = int(os.environ.get("SCRAPE_MAX_ATTEMPTS", 3))
SCRAPE_RETRY_BACKOFF_SECONDS = int(os.environ.get("SCRAPE_RETRY_BACKOFF_SECONDS", 4))

# Confirmed column order for nba.com's box-score table (PLAYER is its own
# cell, handled separately). Used instead of scraping <thead> text so a
# markup tweak there can't silently misalign stats.
STAT_COLUMNS = [
    "MIN", "FGM", "FGA", "FG%", "3PM", "3PA", "3P%", "FTM", "FTA", "FT%",
    "OREB", "DREB", "REB", "AST", "STL", "BLK", "TO", "PF", "PTS", "+/-",
]
