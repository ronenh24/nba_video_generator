import json
import re
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.common.by import By


TIME_TAG = ".//span[starts-with(@class, 'GamePlayByPlayRow_clockElement')]"
DESC_TAG = ".//span[starts-with(@class, 'GamePlayByPlayRow_desc')]"


# ---------------------------------------------------------------- helpers

def gid_from_url(pbp_url: str) -> str:
    # ".../game/bos-vs-phi-0012600018/play-by-play" -> "0012600018"
    return re.search(r"(\d{10})", pbp_url).group(1)


def season_from_game_id(gid: str) -> str:
    # "0012600018" -> "2026-27"
    yy = int(gid[3:5])
    return f"20{yy:02d}-{(yy + 1) % 100:02d}"


def event_url(gid: str, eid: int, desc: str) -> str:
    return ("https://www.nba.com/stats/events?CFID=&CFPARAMS="
            f"&GameEventID={eid}&GameID={gid}"
            f"&Season={season_from_game_id(gid)}&flag=1&title={quote(desc)}")


def clock_to_sec(c: str) -> int:
    # feed format "PT11M45.00S" or row format "11:45" / "0:07.3"
    c = c.strip()
    m = re.match(r"PT(\d+)M([\d.]+)S", c)
    if m:
        return int(m.group(1)) * 60 + int(float(m.group(2)))
    mm, ss = c.split(":")
    return int(mm) * 60 + int(float(ss))


def _key(period: int, sec: int, desc: str):
    return (period, sec, " ".join(desc.split()).lower())


def load_actions(driver, gid: str) -> dict:
    """Return {(period, clock_sec, desc_lower): actionNumber}."""
    actions = None

    # 1) the page's embedded Next.js data
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                  driver.page_source, re.S)
    if m:
        def find(o):
            if isinstance(o, dict):
                a = o.get("actions")
                if isinstance(a, list) and a and "actionNumber" in a[0]:
                    return a
                for v in o.values():
                    r = find(v)
                    if r:
                        return r
            elif isinstance(o, list):
                for v in o:
                    r = find(v)
                    if r:
                        return r
            return None
        actions = find(json.loads(m.group(1)))

    # 2) otherwise fetch the feed from inside the browser
    if not actions:
        url = (
            f"https://cdn.nba.com/static/json/liveData/playbyplay/"
            f"playbyplay_{gid}.json"
        )
        txt = driver.execute_async_script(
            "const cb = arguments[arguments.length-1];"
            "fetch(arguments[0]).then(r => r.text()).then(cb)"
            ".catch(e => cb(''));",
            url,
        )
        if txt:
            actions = json.loads(txt)["game"]["actions"]

    if not actions:
        raise RuntimeError("could not load play-by-play actions")

    lookup = {}
    for a in actions:
        if "description" not in a:
            a["description"] = ""
        k = _key(a["period"], clock_to_sec(a["clock"]), a["description"])
        lookup.setdefault(
            k, a["actionNumber"]
        )  # first one wins on duplicates
    return lookup


# ------------------------------------------------------------------- main

def get_plays(
        driver: webdriver, pbp_url: str, last_name: str,
        data_is_home_team: str
):
    driver.get(pbp_url)

    game_title = driver.title.rstrip(" Play-by-Play | NBA.com").split("vs")
    away = game_title[0].split()[-1]
    home_date = game_title[1]
    date = " ".join(home_date.split()[-3:])
    home = home_date.split()[:-3][-1]
    if data_is_home_team == "true":
        game_title = away + " " + date
    else:
        game_title = home + " " + date
    title = " vs " + game_title + " Full Play"

    body = driver.find_element(By.TAG_NAME, "body").text.lower()

    while "content unavailable" in body:
        driver.refresh()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

    gid = gid_from_url(pbp_url)
    lookup = load_actions(driver, gid)

    tabs = driver.find_elements(
        By.CSS_SELECTOR,
        'nav[class^="GamePlayByPlay_periods"] button'
    )
    result = []
    quarter = 1

    for tab in tabs[:-1]:
        driver.execute_script("arguments[0].click();", tab)

        play_by_play = driver.find_element(By.ID, "playByPlayContainer")
        rows = play_by_play.find_elements(By.TAG_NAME, "article")

        for i, row in enumerate(rows):
            if (
                row.get_attribute("data-is-home-team") == data_is_home_team
                and last_name.lower() in row.text.lower()
            ):
                try:
                    desc_raw = row.find_element(By.XPATH, DESC_TAG).text
                    if not _ball_exception(last_name, desc_raw):
                        continue
                    desc = desc_raw.lower()
                    play_time = clock_to_sec(
                        row.find_element(By.XPATH, TIME_TAG).text
                    )

                    eid = lookup.get(_key(quarter, play_time, desc_raw))
                    if eid is None:
                        continue
                    video_url = event_url(gid, eid, desc_raw)

                    if "free throw 1 of" in desc:
                        try:
                            foul_link, foul_desc = _find_foul_url(
                                rows, i, play_time, gid, lookup, quarter
                            )
                            result.append(
                                (foul_link, foul_desc, quarter, play_time)
                            )
                        except Exception:
                            pass
                    result.append((video_url, desc_raw, quarter, play_time))
                except Exception:
                    pass
        quarter += 1

    result = combine_events(result)

    return title, result


def _ball_exception(last_name, desc):
    if last_name.lower() != "ball":
        return True

    desc = desc.lower()

    if "lost ball" in desc and not desc.startswith("ball "):
        return False

    if "jump ball" in desc and len(desc.split("ball")) < 3:
        return False

    return True


def _find_foul_url(rows, i, play_time, gid, lookup, quarter):
    for j in range(i - 1, -1, -1):
        try:
            t = clock_to_sec(rows[j].find_element(By.XPATH, TIME_TAG).text)
        except Exception:
            continue

        if t != play_time:
            break

        desc_raw = rows[j].find_element(By.XPATH, DESC_TAG).text
        if "foul" in desc_raw.lower():
            eid = lookup.get(_key(quarter, t, desc_raw))
            if eid is not None:
                return event_url(gid, eid, desc_raw), desc_raw

    return None


def combine_events(events, max_gap=2):
    combined = []
    current = None

    i = 0
    while i < len(events):
        url, desc, quarter, time = events[i]
        desc_l = desc.lower()

        is_free_throw = "free throw" in desc_l
        is_off_foul = "offensive foul" in desc_l or "off. foul" in desc_l
        is_timeout = "timeout" in desc_l

        event = {
            "url": url,
            "desc": desc,
            "quarter": quarter,
            "time": time,
        }

        # Skip offensive fouls
        if is_off_foul:
            i += 1
            continue

        # Keep free throws separate
        if is_free_throw:
            if current:
                combined.append((
                    current["url"],
                    current["desc"],
                    current["quarter"],
                    current["time"],
                ))
                current = None

            combined.append((url, desc, quarter, time))
            i += 1
            continue

        # Keep timeouts separate
        if is_timeout:
            if current:
                combined.append((
                    current["url"],
                    current["desc"],
                    current["quarter"],
                    current["time"],
                ))
                current = None

            i += 1
            continue

        if current is None:
            current = event
            i += 1
            continue

        current_desc_l = current["desc"].lower()

        same_quarter = quarter == current["quarter"]
        time_diff = abs(current["time"] - time)

        can_merge = (
            same_quarter
            and time_diff <= max_gap
            and "foul" not in current_desc_l
        )

        if can_merge:
            current["desc"] = f'{current["desc"]}, {desc}'
            current["url"] = url
            current["time"] = max(current["time"], time)
        else:
            combined.append((
                current["url"],
                current["desc"],
                current["quarter"],
                current["time"],
            ))
            current = event

        i += 1

    if current:
        combined.append((
            current["url"],
            current["desc"],
            current["quarter"],
            current["time"],
        ))

    return combined
