"""Play-by-play, game title and game date, read through the browser
(or direct requests)."""
import json
import re
import time

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CDN_HEADERS = {
    "User-Agent": UA, "Referer": "https://www.nba.com/",
    "Accept": "application/json"
}

PBP_CDN = (
    "https://cdn.nba.com/static/json/liveData/playbyplay/"
    "playbyplay_{gid}.json"
)
PBP_STATS = "https://stats.nba.com/stats/playbyplayv3"
STATS_HEADERS = {
    "Host": "stats.nba.com",
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}


# ============================================================ play-by-play
def get_pbp(gid: str) -> list:
    """CDN first (works from almost anywhere), stats.nba.com as fallback."""
    try:
        r = requests.get(
            PBP_CDN.format(gid=gid), headers=CDN_HEADERS, timeout=30
        )
        r.raise_for_status()
        return r.json()["game"]["actions"]
    except Exception as e:
        print(f"CDN play-by-play failed ({e}); trying stats.nba.com ...")
    r = requests.get(
        PBP_STATS,
        headers=STATS_HEADERS,
        timeout=(5, 15),
        params={"GameID": gid, "StartPeriod": 0, "EndPeriod": 0},
    )
    r.raise_for_status()
    return r.json()["game"]["actions"]


def _find_actions(obj):
    """Recursively find the play-by-play action list inside arbitrary JSON."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and "actionNumber" in obj[0]:
            return obj
        for x in obj:
            r = _find_actions(x)
            if r:
                return r
    elif isinstance(obj, dict):
        for v in obj.values():
            r = _find_actions(v)
            if r:
                return r
    return None


JS_FETCH_JSON = """
var url = arguments[0];
var cb = arguments[arguments.length - 1];
fetch(url)
  .then(r => {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.text();
  })
  .then(t => cb(t))
  .catch(e => cb("ERROR: " + e.message));
"""


def get_pbp_browser(driver, gid: str) -> list:
    """Play-by-play via the real browser. Three strategies, in order."""
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.get_log("performance")  # clear old entries
    except Exception:
        pass

    driver.get(f"https://www.nba.com/game/{gid}/play-by-play")
    WebDriverWait(driver, 30).until(
        lambda d: d.find_element(By.TAG_NAME, "body").text.strip() != "")
    time.sleep(4)  # let the page's own data requests finish

    # a) data the page embeds for itself
    raw = driver.execute_script(
        "var e=document.getElementById('__NEXT_DATA__'); "
        "return e ? e.textContent : null;"
    )
    if raw:
        try:
            actions = _find_actions(json.loads(raw))
            if actions:
                print("Play-by-play loaded from the game page data.")
                return actions
        except Exception as e:
            print(f"  could not parse page data: {e}")

    # b) sniff the network responses the page itself received
    try:
        for entry in driver.get_log("performance"):
            msg = json.loads(entry["message"])["message"]
            if msg.get("method") != "Network.responseReceived":
                continue
            resp = msg["params"]["response"]
            url = resp.get("url", "")
            if "playbyplay" not in url.lower():
                continue
            try:
                body = driver.execute_cdp_cmd(
                    "Network.getResponseBody",
                    {"requestId": msg["params"]["requestId"]}
                )
                actions = _find_actions(json.loads(body["body"]))
                if actions:
                    print(
                        f"Play-by-play captured from page request: {url[:90]}"
                    )
                    return actions
            except Exception:
                continue
    except Exception as e:
        print(f"  network sniffing failed: {e}")

    # c) fetch the CDN file from inside the nba.com page
    try:
        driver.set_script_timeout(60)
        txt = driver.execute_async_script(
            JS_FETCH_JSON, PBP_CDN.format(gid=gid)
        )
        if txt and not txt.startswith("ERROR:"):
            actions = _find_actions(json.loads(txt))
            if actions:
                print("Play-by-play loaded via in-page fetch.")
                return actions
    except Exception:
        pass


def get_game_title(driver, gid: str) -> str:
    """Video title taken from the play-by-play page (page title / og:title)."""
    try:
        if "play-by-play" not in driver.current_url:
            driver.get(f"https://www.nba.com/game/{gid}/play-by-play")
            WebDriverWait(driver, 30).until(
                lambda d: d.find_element(
                    By.TAG_NAME, "body"
                ).text.strip() != "")
        t = driver.execute_script(
            "var m=document.querySelector('meta[property=\"og:title\"]'); "
            "return (m && m.content) || document.title || '';"
        ) or ""
    except Exception:
        t = ""
    t = re.sub(r"\s*[|\u2013-]\s*NBA(\.com)?\s*$", "", t.strip(), flags=re.I)
    t = re.sub(r"\bplay[- ]by[- ]play\b", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" |-\u2013:,")
    return t or f"NBA game {gid}"


MONTH_RE = (
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+"
    r"\d{1,2},?\s+\d{4}"
)


def _find_date_in_json(obj):
    """Look for a game date in the page JSON;
    returns a datetime.date or None."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    local_keys = ("gameEt", "gameDateEst", "gameTimeEst", "gameDate")
    utc_keys = ("gameTimeUTC", "gameDateTimeUTC")
    found = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}", v):
                    found.setdefault(k, v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(obj)
    for k in local_keys:
        if k in found:
            return datetime.strptime(found[k][:10], "%Y-%m-%d").date()
    for k in utc_keys:
        if k in found:
            dt = datetime.fromisoformat(found[k].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(ZoneInfo("America/New_York")).date()
    return None


def get_game_date(driver, gid: str) -> str:
    """Game date as 'Oct 5, 2026', from the play-by-play page.
    '' if not found."""
    try:
        if "play-by-play" not in driver.current_url:
            driver.get(f"https://www.nba.com/game/{gid}/play-by-play")
            WebDriverWait(driver, 30).until(
                lambda d: d.find_element(
                    By.TAG_NAME, "body"
                ).text.strip() != "")
            time.sleep(2)
        raw = driver.execute_script(
            "var e=document.getElementById('__NEXT_DATA__'); "
            "return e ? e.textContent : null;"
        )
        if raw:
            d = _find_date_in_json(json.loads(raw))
            if d:
                return f"{d.strftime('%b')} {d.day}, {d.year}"
        text = driver.execute_script(
            "var m=document.querySelector('meta[property=\"og:title\"]'); "
            "return [(m&&m.content)||'', document.title||'', "
            "(document.body.innerText||'').slice(0,3000)].join(' ');"
        ) or ""
        m = re.search(MONTH_RE, text)
        if m:
            return re.sub(r"\s+", " ", m.group(0)).replace(".", "")
    except Exception as e:
        print(f"  could not read game date: {e}")
    return ""
