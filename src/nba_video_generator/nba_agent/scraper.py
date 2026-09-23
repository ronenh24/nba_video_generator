"""Scrape nba.com's daily schedule and box scores.

NOTE: nba.com's markup can change. This targets the structure of the
GameBoxscore_* / StatsTable_* components as of this writing (the same
component classes you'll see if you save a box score page's HTML). If the
site changes, the CSS selectors below are the only things that should need
updating.
"""
import functools
import re
import time

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .config import BASE_GAMES_URL, SCRAPE_MAX_ATTEMPTS, SCRAPE_RETRY_BACKOFF_SECONDS, STAT_COLUMNS


def _retry_scrape(description: str, default_factory):
    """Decorator: retries a scrape function, reloading and backing off,
    whenever it either raises (timeout / driver error) or comes back empty
    (page loaded but nba.com hadn't finished hydrating it yet). Each retry
    calls the wrapped function again from scratch, which re-navigates via
    driver.get(url) — effectively a fresh page load, not a stale re-render.
    Gives up after SCRAPE_MAX_ATTEMPTS and returns the emptiest safe default
    (an empty list/dict) so callers never see an exception, just "nothing
    found here."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(driver, *args, **kwargs):
            result = default_factory()
            for attempt in range(1, SCRAPE_MAX_ATTEMPTS + 1):
                try:
                    result = fn(driver, *args, **kwargs)
                    if result:
                        return result
                    print(
                        f"    ! {description}: loaded but empty "
                        f"(attempt {attempt}/{SCRAPE_MAX_ATTEMPTS})"
                    )
                except (TimeoutException, WebDriverException) as e:
                    print(
                        f"    ! {description}: {e.__class__.__name__} "
                        f"(attempt {attempt}/{SCRAPE_MAX_ATTEMPTS})"
                    )

                if attempt < SCRAPE_MAX_ATTEMPTS:
                    wait = SCRAPE_RETRY_BACKOFF_SECONDS * attempt
                    print(f"      retrying in {wait}s...")
                    time.sleep(wait)

            print(f"    ! {description}: giving up after {SCRAPE_MAX_ATTEMPTS} attempts")
            return result

        return wrapper

    return decorator


@_retry_scrape("fetching schedule", default_factory=list)
def get_boxscore_urls_for_date(driver, date: str) -> list[str]:
    """Return box-score page URLs for every game on `date` (YYYY-MM-DD)."""
    driver.get(BASE_GAMES_URL.format(date=date))
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/game/']"))
    )
    time.sleep(1.5)  # let late-loading game cards settle

    hrefs = set()
    for a in driver.find_elements(By.CSS_SELECTOR, "a[href*='/game/']"):
        href = a.get_attribute("href")
        if not href:
            continue
        m = re.match(r"(https://www\.nba\.com/game/[a-z\-]+-\d+)", href)
        if m:
            hrefs.add(m.group(1))

    return [f"{h}/box-score" for h in sorted(hrefs)]


@_retry_scrape("parsing box score", default_factory=dict)
def parse_boxscore(driver, url: str) -> dict[str, list[dict]]:
    """Load a box-score page and return {team_full_name: [player_stat_dict, ...]}.
    Returns {} (triggering a retry) if fewer than 2 teams were parsed, since
    that almost always means the page hadn't finished rendering."""
    driver.get(url)
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
    time.sleep(1)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    teams: dict[str, list[dict]] = {}

    for block in soup.select("section.GameBoxscore_gbTableSection__jI4Mm"):
        header = block.select_one("h2")
        table = block.select_one("table")
        if not header or not table:
            continue

        team_name = header.get_text(strip=True)

        rows = []
        for tr in table.select("tbody tr"):
            name_span = tr.select_one("[class*='gbpNameFull']")
            if not name_span:
                continue  # totals row, or a row with no player name
            if tr.select_one("[class*='GameBoxscoreTable_comment']"):
                continue  # "DNP - Coach's Decision" row

            cells = tr.select("td[class*='GameBoxscoreTable_stat']")
            values = [c.get_text(strip=True) for c in cells]
            # A player who logs 0 minutes has no "+/-" cell at all, so pad
            # missing trailing values rather than let zip() silently drop
            # the last (often meaningful) columns.
            if len(values) < len(STAT_COLUMNS):
                values += [""] * (len(STAT_COLUMNS) - len(values))

            stats = dict(zip(STAT_COLUMNS, values))
            stats["PLAYER"] = name_span.get_text(strip=True)
            rows.append(stats)

        teams[team_name] = rows

    if len(teams) != 2:
        return {}  # treated as "empty" by the retry decorator

    return teams
