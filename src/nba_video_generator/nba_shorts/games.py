"""Discover the games played on a given day from nba.com/games."""
import re
import time

GAME_LINK_RE = re.compile(r"/game/[^?#\s]*?(\d{10})(?:[/?#]|$)")


def discover_games(driver, d) -> list:
    """Game IDs listed on https://www.nba.com/games?date=YYYY-MM-DD (in page order)."""
    url = f"https://www.nba.com/games?date={d:%Y-%m-%d}"
    print(f"Loading {url}")
    driver.get(url)
    js = ("return Array.from(document.querySelectorAll('a[href*=\"/game/\"]'))"
          ".map(a => a.href);")
    hrefs = []
    for _ in range(25):  # wait up to ~25s for the scoreboard to render
        hrefs = driver.execute_script(js) or []
        if hrefs:
            break
        time.sleep(1)
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    hrefs += driver.execute_script(js) or []

    ids = []
    for h in hrefs:
        m = GAME_LINK_RE.search(h)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    if not ids:  # fallback: gameId values in the embedded page data
        raw = driver.execute_script(
            "var e=document.getElementById('__NEXT_DATA__'); return e ? e.textContent : '';") or ""
        for gid in re.findall(r'"gameId"\s*:\s*"(\d{10})"', raw):
            if gid not in ids:
                ids.append(gid)
    return ids

