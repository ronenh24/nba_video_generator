"""Discover the finished games played on a given day from nba.com/games."""
import json
import logging
import re
import time
from datetime import date

log = logging.getLogger(__name__)

GAME_LINK_RE = re.compile(r"/game/[^?#\s]*?(?<!\d)(\d{10})(?!\d)(?:[/?#]|$)")
STATUS_FINAL = 3  # data-game-status / gameStatus: 1 = scheduled, 2 = live, 3 = final

# One entry per game card: the status code and the href of the enclosing game link.
CARDS_JS = r"""
return Array.from(document.querySelectorAll('[data-game-status]')).map(el => {
  const a = el.closest('a[href*="/game/"]');
  return {href: a ? a.href : '',
          status: parseInt(el.getAttribute('data-game-status'), 10)};
});
"""

NEXT_DATA_JS = ("var e=document.getElementById('__NEXT_DATA__');"
                "return e ? e.textContent : '';")


def _collect_cards(driver):
    return driver.execute_script(CARDS_JS) or []


def _wait_for_stable_cards(driver, timeout=25, stable_for=2):
    """Poll until cards appear and the count stops changing for `stable_for` ticks."""
    last, stable, cards = -1, 0, []
    for _ in range(timeout):
        cards = _collect_cards(driver)
        if cards and len(cards) == last:
            stable += 1
            if stable >= stable_for:
                break
        else:
            stable = 0
        last = len(cards)
        time.sleep(1)
    return cards


def _final_ids_from_next_data(raw: str) -> list[str]:
    """Fallback: walk the embedded JSON for dicts with a gameId and gameStatus == 3."""
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    found = []

    def walk(o):
        if isinstance(o, dict):
            gid = o.get("gameId")
            if (isinstance(gid, str) and re.fullmatch(r"\d{10}", gid)
                    and o.get("gameStatus") == STATUS_FINAL):
                found.append(gid)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return list(dict.fromkeys(found))


def discover_games(driver, d: date) -> list[str]:
    """Finished game IDs listed on https://www.nba.com/games?date=YYYY-MM-DD (page order)."""
    url = f"https://www.nba.com/games?date={d:%Y-%m-%d}"
    log.info("Loading %s", url)
    driver.get(url)

    _wait_for_stable_cards(driver)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    cards = _collect_cards(driver)  # re-read after scrolling to catch lazy cards

    all_ids, finished = [], []
    for c in cards:
        m = GAME_LINK_RE.search(c["href"])
        if not m:
            continue
        gid = m.group(1)
        if gid not in all_ids:
            all_ids.append(gid)
        if c["status"] == STATUS_FINAL and gid not in finished:
            finished.append(gid)

    if not all_ids:  # DOM yielded nothing: try structured data
        finished = _final_ids_from_next_data(driver.execute_script(NEXT_DATA_JS) or "")
        if finished:
            log.warning("No cards in DOM; used __NEXT_DATA__ fallback (%d ids)", len(finished))
        else:
            log.warning("No games found for %s (off day, blocked, or page changed?)", d)
    else:
        log.info("%d finished of %d games for %s", len(finished), len(all_ids), d)
    return finished

