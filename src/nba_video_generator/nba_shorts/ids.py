"""Game-ID, season and date helpers."""
import re
from urllib.parse import quote


# ============================================================ game id helpers
def get_game_id(arg: str) -> str:
    """Accepts a 10-digit game ID or any nba.com URL containing one."""
    m = re.search(r"(\d{10})", arg)
    if not m:
        raise ValueError(f"Could not find a 10-digit game ID in: {arg}")
    return m.group(1)


def season_from_game_id(gid: str) -> str:
    """'0012600055' -> '2026-27'; '0022500123' -> '2025-26'."""
    yy = int(gid[3:5])
    return f"20{yy:02d}-{(yy + 1) % 100:02d}"


def game_type(gid: str) -> str:
    return {"1": "preseason", "2": "regular season", "4": "playoffs",
            "5": "play-in", "6": "NBA Cup final"}.get(gid[2], "unknown")


def event_url(gid: str, eid: int, desc: str) -> str:
    return ("https://www.nba.com/stats/events?CFID=&CFPARAMS="
            f"&GameEventID={eid}&GameID={gid}"
            f"&Season={season_from_game_id(gid)}&flag=1&title={quote(desc)}")


def parse_date(text: str):
    """'today', 'yesterday', 2026-10-05, 10/05/2026, 'Oct 5, 2026'
    -> datetime.date"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    t = text.strip()
    now_et = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    if t.lower() == "today":
        return now_et
    if t.lower() == "yesterday":
        return now_et - timedelta(days=1)
    for fmt in (
        "%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y",
        "%B %d, %Y", "%b %d %Y", "%B %d %Y"
    ):
        try:
            return datetime.strptime(t.replace(".", ""), fmt).date()
        except ValueError:
            pass
    raise ValueError(
        f"Could not understand date: {text!r} (try 2026-10-05, yesterday, "
        "or 'Oct 5, 2026')")
