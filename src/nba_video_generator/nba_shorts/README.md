# nba-shorts

Find highlight-worthy plays in NBA games, download the clips through a real Chrome
window, and optionally convert to 9:16 and compile one video per game.

Needs Chrome, and ffmpeg on PATH for `--vertical` / `--compile`.

## Install

    pip install -e .

## Command line

    nba-shorts 0012600055 --dry-run
    nba-shorts 0012600055 --top 8 --vertical --compile
    nba-shorts --date yesterday --vertical --compile        # every game on nba.com/games
    python -m nba_shorts --date "Oct 5, 2026" --max-games 2

## As a module

    from nba_shorts import Config, make_shorts, make_shorts_for_date, find_top_plays, list_games

    cfg = Config(top=6, vertical=True, compilation=True, compiled_dir="shorts")

    result = make_shorts("0012600055", cfg)          # one game (ID or URL)
    print(result.title, result.compiled, result.clips)

    results = make_shorts_for_date("2026-10-05", cfg)  # whole day
    for r in results:
        print(r.game_id, r.compiled or r.error)

    plays = find_top_plays("0012600055", Config(top=5))  # picks only, no downloads
    for p in plays:
        print(p.score, p.period, p.clock, p.description, p.reasons)

    print(list_games("yesterday"))                    # just the game IDs

To reuse one Chrome window across calls:

    from nba_shorts import open_browser
    with open_browser() as driver:
        make_shorts("0012600055", cfg, driver=driver)
        make_shorts("0012600056", cfg, driver=driver)

## Layout

    nba_shorts/
        config.py      Config dataclass
        ids.py         game id / season / date parsing
        playbyplay.py  play-by-play, title and date from the game page
        scoring.py     score_play, pick_plays, Play
        browser.py     Chrome driver and clip downloads
        video.py       ffmpeg 9:16 conversion and compilation
        games.py       game discovery from nba.com/games
        core.py        make_shorts, make_shorts_for_date, ...
        cli.py         command line
