"""Map the full team names shown on nba.com box scores to the lowercase
tri-codes your pipeline() / get_pbp_beta already expect (e.g. "phx", "lal")."""

TEAM_ABBR = {
    "Atlanta Hawks": "atl",
    "Boston Celtics": "bos",
    "Brooklyn Nets": "bkn",
    "Charlotte Hornets": "cha",
    "Chicago Bulls": "chi",
    "Cleveland Cavaliers": "cle",
    "Dallas Mavericks": "dal",
    "Denver Nuggets": "den",
    "Detroit Pistons": "det",
    "Golden State Warriors": "gsw",
    "Houston Rockets": "hou",
    "Indiana Pacers": "ind",
    "LA Clippers": "lac",
    "Los Angeles Clippers": "lac",
    "Los Angeles Lakers": "lal",
    "Memphis Grizzlies": "mem",
    "Miami Heat": "mia",
    "Milwaukee Bucks": "mil",
    "Minnesota Timberwolves": "min",
    "New Orleans Pelicans": "nop",
    "New York Knicks": "nyk",
    "Oklahoma City Thunder": "okc",
    "Orlando Magic": "orl",
    "Philadelphia 76ers": "phi",
    "Phoenix Suns": "phx",
    "Portland Trail Blazers": "por",
    "Sacramento Kings": "sac",
    "San Antonio Spurs": "sas",
    "Toronto Raptors": "tor",
    "Utah Jazz": "uta",
    "Washington Wizards": "was",
}


def abbr_for(team_full_name: str) -> str:
    name = team_full_name.strip()
    if name in TEAM_ABBR:
        return TEAM_ABBR[name]
    for full, code in TEAM_ABBR.items():
        if name.lower() == full.lower():
            return code
    raise KeyError(f"Unknown team name: {team_full_name!r} — add it to TEAM_ABBR.")
