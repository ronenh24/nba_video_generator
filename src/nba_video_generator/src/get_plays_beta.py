from selenium import webdriver
from selenium.webdriver.common.by import By


time_tag = ".//span[starts-with(@class, 'GamePlayByPlayRow_clockElement')]"
desc_tag = ".//span[starts-with(@class, 'GamePlayByPlayRow_desc')]"


def get_plays(driver: webdriver, pbp_url: str, last_name: str, data_is_home_team: str):
    driver.get(pbp_url)

    title = last_name + " " + driver.title.rstrip(" Play-by-Play | NBA.com") + " Full Play"

    body = driver.find_element(By.TAG_NAME, "body").text.lower()

    while "content unavailable" in body:
        driver.refresh()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

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
            if row.get_attribute("data-is-home-team") == data_is_home_team and last_name in row.text:
                try:
                    desc_raw = row.find_element(By.XPATH, desc_tag).text
                    desc = desc_raw.lower()
                    play_time = row.find_element(By.XPATH, time_tag).text
                    if play_time.startswith("0"):
                        play_time = play_time[1:]
                    play_time = int(play_time.split(":")[0]) * 60 + int(play_time.split(":")[1])
                    link = row.find_element(By.TAG_NAME, "a")
                    video_url = link.get_attribute("href")
                    if "free throw 1 of" in desc:
                        try:
                            foul_link, foul_desc = _find_foul_url(rows, i, play_time)
                            result.append(
                                (
                                    foul_link,
                                    foul_desc,
                                    quarter,
                                    play_time,
                                )
                            )
                        except Exception:
                            pass
                    result.append(
                        (
                            video_url,
                            desc_raw,
                            quarter,
                            play_time
                        )
                    )
                except Exception:
                    pass
        quarter += 1

    result = combine_events(result)

    return title, result


def _find_foul_url(rows, i, play_time):
    for j in range(i - 1, -1, -1):
        try:
            t = rows[j].find_element(By.XPATH, time_tag).text
            if t.startswith("0"):
                t = t[1:]
            t = int(t.split(":")[0]) * 60 + int(t.split(":")[1])
        except:
            continue

        if t != play_time:
            break

        desc = rows[j].find_element(By.XPATH, desc_tag).text.lower()
        if "foul" in desc:
            link = rows[j].find_element(By.TAG_NAME, "a")
            return link.get_attribute("href"), rows[j].find_element(By.XPATH, desc_tag).text

    return None


def combine_events(events, max_gap=5):
    combined = []
    current = None

    i = 0
    while i < len(events):
        url, desc, quarter, time = events[i]
        desc_l = desc.lower()

        is_free_throw = "free throw" in desc_l
        is_foul = "foul" in desc_l
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
