# NBA Daily Highlights Agent

Drops into your existing `nba_video_generator` project. Every run:

1. **Scrape** — `nba_agent/scraper.py` opens `nba.com/games?date=YYYY-MM-DD`,
   collects every game's box-score URL, and parses each team's stat table
   (using the same component structure you already worked with).
2. **Pre-filter** — `nba_agent/significance.py` flags any player who clears
   a stat threshold (30+ PTS, 15+ REB, 10+ AST, 5+ STL/BLK, 6+ threes, or a
   triple-double). This is a cheap rule pass so the LLM only sees real
   candidates, not all ~300 players who played that night.
3. **Judge** — the candidates are handed to a local **Ollama** model, which
   picks the ones that are genuinely highlight-worthy (and skips garbage-time
   stat padding in a blowout) and gives a one-line reason for each.
4. **Generate** — for every pick, `nba_agent/orchestrator.py` calls your
   existing `nba_video_generator.beta_search.pipeline()` unchanged, passing
   `(last_name, date, date, team_abbr)` — exactly the format your
   `beta_search.py` already expects.
5. **De-dupe** — a `processed_performances.json` state file tracks which
   (player, team) pairs already got a video on a given date, so re-running
   the agent (e.g. once in the morning, once at night for late West Coast
   games) never regenerates the same clip.

## Setup

```bash
# 1. Install Ollama and pull a model (one-time)
#    https://ollama.com/download
ollama pull llama3.1

# 2. Install the extra Python deps
pip install -r requirements_agent.txt

# 3. Make sure ChromeDriver matches your installed Chrome version
#    (same requirement your existing pipeline already has)
```

Drop `nba_agent/` and `run_agent.py` next to your existing
`nba_video_generator` package (i.e. so `import nba_video_generator...` still
resolves), then set `FFMPEG_PATH` in `nba_agent/config.py` (or via the
`FFMPEG_PATH` environment variable) to your ffmpeg binary.

## Run

```bash
# Process today's completed games once
python run_agent.py

# Process a specific past date
python run_agent.py --date 2026-09-21

# Run continuously, checking once a day at 4am local time
# (games finish late — pick a time after the last West Coast game ends)
python run_agent.py --loop --at 04:00
```

## Notes / things you'll likely need to tune

- **Scraper selectors** (`nba_agent/scraper.py`) target the
  `GameBoxscore_*` / `StatsTable_*` component classes visible in the box
  score HTML. If nba.com ships a redesign, only this file's CSS selectors
  should need updating — nothing else in the pipeline changes.
- **`TEAM_ABBR`** in `nba_agent/team_map.py` covers all 30 teams; extend it
  if nba.com ever renders a team name differently than listed there.
- **Thresholds** in `nba_agent/config.py` are a starting point — tighten
  them (e.g. PTS ≥ 35) if you want fewer, more selective videos, or loosen
  them to catch more borderline performances for the LLM to weigh in on.
- **Rate/etiquette**: this hits nba.com once for the schedule page plus once
  per game for the box score, each day. Keep it to the one daily run rather
  than polling continuously, and check nba.com's terms of use for your
  intended usage.
- **Same-name players**: the pipeline is keyed on last name only (as your
  original `beta_search.py` does), so two active players sharing a surname
  on the *same* team+date could collide. Rare, but worth knowing.
