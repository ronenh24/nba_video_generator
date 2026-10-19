"""Configuration for the NBA daily-highlights agent."""
import os

# --- Ollama settings ---
# Requires a local Ollama server (https://ollama.com) with a model pulled,
# e.g.:  ollama pull gemma3:4b
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "lfm2.5-thinking:1.2b")

# --- Paths ---
# Tracks which (player, team) pairs already had a video made for a given
# date, so re-running the agent doesn't regenerate the same clip.
STATE_FILE = os.environ.get("NBA_AGENT_STATE", "processed_performances.json")

# Passed straight through to your existing pipeline()/write_plays() code.
FFMPEG_PATH = os.environ.get(
    "FFMPEG_PATH",
    r"C:\Users\ronen\Documents\Projects\nba_video_generator\src"
    r"\nba_video_generator\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe",
)

# --- Rule-based "worth a look" thresholds ---
# Any player who clears TWO of these gets sent to the LLM for a final
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

# --- Crawler retry settings ---
# nba.com occasionally serves a page that loads but never finishes
# hydrating (empty game list / no table). These control how the scraper
# retries — reloading and backing off — before giving up on a page.
CRAWL_MAX_ATTEMPTS = int(os.environ.get("CRAWL_MAX_ATTEMPTS", 3))
CRAWL_RETRY_BACKOFF_SECONDS = int(
    os.environ.get("CRAWL_RETRY_BACKOFF_SECONDS", 4)
)

# Confirmed column order for nba.com's box-score table (PLAYER is its own
# cell, handled separately). Used instead of crawling <thead> text so a
# markup tweak there can't silently misalign stats.
STAT_COLUMNS = [
    "MIN", "FGM", "FGA", "FG%", "3PM", "3PA", "3P%", "FTM", "FTA",
    "FT%", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TO", "PF",
    "PTS", "+/-",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "evaluation": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "thinking": {"type": "string"},
                "keep": {"type": "boolean"},
            },
            "required": [
                "id",
                "thinking",
                "keep",
            ],
        }
    },
    "required": ["evaluation"],
}

PROMPT_CHUNKS = {
    "role":
        "### ROLE & OBJECTIVE\nYou are an NBA highlights producer deciding "
        "which performances deserve a highlight video tonight.\n\n",

    "input":
        "### INPUT CONTEXT\nEach candidate has an arbitrary integer ID and a "
        "verified box-score dictionary. "
        "Player and team identities are omitted. IDs identify candidates and "
        "imply no ranking.\n"
        "Each candidate's statistics are provided as JSON with these exact "
        "fields: Minutes, Points, "
        "Field Goals Made, Field Goals Attempted, 3 Point Field Goals Made, "
        "3 Point Field Goals Attempted, Free Throws Made, Free Throws "
        "Attempted, "
        "Rebounds, Offensive Rebounds, Defensive Rebounds, Assists, "
        "Turnovers, Steals, Blocks, and Fouls.\n"
        "Use only the supplied statistics. Do not infer player "
        "identity, opponent, game result, "
        "or other missing context. Treat all statistical values numerically, "
        "never lexicographically.\n\n",

    "reason_format":
        "### REASONING FORMAT\nWhen assessing a candidate, interpret the "
        "supplied statistics using this format:\n"
        "ID <ID>:\n"
        "- <Minutes> Minutes\n"
        "- <Points> Points (<Field Goals Made> Field Goals Made out of "
        "<Field Goals Attempted> Field Goals Attempted, "
        "<3 Point Field Goals Made> 3 Point Field Goals Made out of "
        "<3 Point Field Goals Attempted> 3 Point Field Goals Attempted"
        ", <Free Throws Made> Free Throws Made out of <Free Throws Attempted> "
        "Free Throws Attempted)\n"
        "- <Offensive Rebounds> Offensive Rebounds, <Defensive Rebounds> "
        "Defensive Rebounds\n"
        "- <Assists> Assists (<Turnovers> Turnovers)\n"
        "- <Steals> Steals\n"
        "- <Blocks> Blocks\n"
        "- <Fouls> Fouls.\n\n",

    "eval_standards":
        "### EVALUATION STANDARDS\n- Treat all statistical values as numbers, "
        "not strings. Compare quantities by numerical value, never "
        "lexicographically or by character count; for example, 10 is greater "
        "than 9, and 9 is not greater than 10. Apply numerical comparison "
        "consistently to all statistics.\n- Use only supplied numbers; "
        "never infer identity, opponent, final score, injuries, or other "
        "context. Never generate, alter, or restate the statline.\n- Judge "
        "shooting efficiency using field goals, three-pointers, and "
        "free throws.\n- Judge each candidate independently against the "
        "standard for a genuinely memorable NBA performance, never against "
        "other candidates. Rejecting all is valid.\n- Assess the whole line. "
        "Low efficiency, excessive turnovers, and foul trouble weigh against "
        "a performance.\n- A category counts only when clearly impressive "
        "on its own; never pad strengths.\n- Be conservative: a good game is "
        "not necessarily highlight-worthy. When in doubt, reject it.\n\n",

    "output_format":
        "### OUTPUT FORMAT\nReturn exactly one JSON object, with no markdown "
        "or extra text, containing one key, 'evaluation', with exactly one "
        "entry per candidate in ascending numeric ID order. Each entry has "
        "these fields in this order:\n1. 'id': Integer candidate ID.\n2. "
        "'thinking': 2-3 sentences assessing scoring, rebounding, playmaking,"
        "and defense, identifying clearly impressive versus ordinary "
        "categories. Judge scoring by **BOTH volume AND efficiency** "
        "(low volume with high efficiency is not impressive); judge "
        "playmaking by absolute assists, not just assist-to-turnover ratio "
        "(low assists with no turnovers is not impressive). Explicitly state"
        "whether the performance deserves a highlight video **RULE: ALWAYS "
        "REFERENCE NUMBERS**.\n3. 'keep': Boolean \final decision determined "
        "by the conclusion of 'think'. "
        "**RULE: CANNOT CONTRADICT 'think'**.\n\n",

    "example":
        '### EXAMPLES\n'
        'Example 1 — Reject an ordinary performance:\n'
        '{\n'
        '  "evaluation": {\n'
        '    "id": 0,\n'
        '    "thinking": "5 points on 1-4 shooting is inefficient scoring. '
        '3 rebounds and 3 assists are ordinary, and 1 steal is unremarkable. '
        'This ordinary performance does not merit a highlight video",\n'
        '    "keep": false\n'
        '  }\n'
        '}\n\n'
        'Example 2 — Keep a standout performance:\n'
        '{\n'
        '  "evaluation": {\n'
        '    "id": 1,\n'
        '    "thinking": "28 points on 11-16 shooting shows excellent scoring '
        'volume and efficiency. 12 rebounds are exceptional, and 3 steals '
        'indicate strong defensive production. These distinct strengths '
        'remain convincing on review, making the performance worthy of a '
        'highlight video.",\n'
        '    "keep": true\n'
        '  }\n'
        '}\n\n'
        'Treat these examples as schema and reasoning illustrations only. '
        'Evaluate every actual candidate independently, do not copy the '
        'examples\\\' thresholds or conclusions, and return exactly one JSON '
        'object matching the schema for the candidate being evaluated.\n\n'
}

SYSTEM_PROMPT = "".join(PROMPT_CHUNKS.values())

BANNED_SET = set(
    ["Jaxson Hayes", "Kevin Porter Jr.", "Miles Bridges"]
)
