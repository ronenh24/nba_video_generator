from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
import math
from unidecode import unidecode


box_score_tag = '//table[starts-with(@class, "StatsTable_table")]'
name_tag = './/span[@class = "GameBoxscoreTablePlayer_gbpNameFull__cf_sn"]'
time_tag = ".//span[starts-with(@class, 'GamePlayByPlayRow_clockElement')]"


def get_player_urls(
    driver: webdriver, player_name: str, box_score: str, td_vals: list[int]
) -> tuple[str, str, list[tuple[int, str]]]:
    """
    Parses box score for player event links.

    Returns list of player event (int) and link.
    
    Example: [("3", link to fg made), ("14", link to reb)]
    """
    driver.get(box_score)
    title = player_name + " Full Highlights " + driver.title.rstrip(" Box Scores | NBA.com")
    stats = ""
    body = driver.find_element(By.TAG_NAME, "body").text.lower()

    while "content unavailable" in body:
        driver.refresh()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

    urls = []
    tables = driver.find_elements(By.XPATH, box_score_tag)
    for table in tables:
        rows = table.find_elements(By.TAG_NAME, "tr")
        for row in rows:
            try:
                name = row.find_element(
                    By.XPATH,
                    name_tag
                )
                if name.text == player_name:
                    for td_val in td_vals:
                        try:
                            event = row.find_element(
                                By.XPATH, "./td[" + str(td_val) + "]"
                            )
                            event_url = event.find_element(
                                By.TAG_NAME, "a"
                                ).get_attribute("href")
                            urls.append((td_val, event_url))
                        except Exception:
                            if td_val == 19:
                                urls.append((td_val, ""))
                    td_elems = row.find_elements(By.TAG_NAME, "td")
                    stats = [td.text for td in td_elems]
                    stats = format_box_score(stats)
                    print(stats)
                    return title, stats, urls
            except Exception:
                pass

    return title, stats, urls


def format_box_score(stats: list[str]) -> str:

    min_played   = stats[1]
    fgm, fga     = stats[2], stats[3]
    three_fgm, three_fga = stats[5], stats[6]
    ftm, fta     = stats[8], stats[9]
    off_reb      = stats[11]
    def_reb      = stats[12]
    total_reb    = stats[13]
    ast          = stats[14]
    stl          = stats[15]
    blk          = stats[16]
    tov          = stats[17]
    pf           = stats[18]
    pts          = stats[19]
    plus_minus   = stats[20]

    if int(plus_minus) > 0:
        plus_minus = "+" + plus_minus

    return (
        f"{min_played} Minutes, "
        f"{pts} Points ({fgm}-{fga} FG, {three_fgm}-{three_fga} 3PT, {ftm}-{fta} FT), "
        f"{total_reb} Rebounds ({off_reb} OFF, {def_reb} DEF), "
        f"{ast} Assists ({tov} Turnovers), "
        f"{stl} Steals, "
        f"{blk} Block, "
        f"{pf} Personal Fouls, "
        f"{plus_minus}"
    )


def get_ft_urls(
    driver: webdriver, player_name: str, pbp: str, url: str, include_two: bool = True
) -> list[tuple[str, str]]:
    """
    Parses play by play for player free throw links.

    Returns list of player free throw link and quarter.
    """
    if player_name == "Hansen Yang":
        player_name = "Yang Hansen"

    player_name = unidecode(player_name)

    times = _get_ft_times(driver, player_name, pbp, include_two)

    last_name = player_name.split()[-1]

    video_urls = []

    for quarter, fouls in times.items():
        driver.get(url + quarter)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

        while "content unavailable" in body:
            driver.refresh()
            body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "OT" in quarter:
            quarter = str(4 + int(quarter.lstrip("OT")))
        else:
            quarter = quarter[1]
        play_by_play = driver.find_element(By.ID, "playByPlayContainer")
        rows = play_by_play.find_elements(By.TAG_NAME, "article")
        for i, row in enumerate(rows):
            time = row.find_element(By.XPATH, time_tag).text
            if time.startswith("0"):
                time = time[1:]
            if time == fouls[0]:
                event_text = row.text
                if ".FOUL" in event_text or \
                        last_name + " Free Throw" in event_text:
                    try:
                        event = row.find_element(
                            By.TAG_NAME, "a"
                        ).get_attribute("href")
                        video_urls.append((event, quarter))
                    except Exception:
                        pass
                if i < len(rows) - 1:
                    next_time = rows[i + 1].find_element(
                        By.XPATH, time_tag
                    ).text
                    if next_time.startswith("0"):
                        next_time = next_time[1:]
                    current_foul_secs = time_to_secs(fouls[0])
                    next_time_secs = time_to_secs(next_time)
                    if current_foul_secs != next_time_secs:
                        fouls.pop(0)
            if len(fouls) == 0:
                break

    return video_urls


def _get_ft_times(
    driver: webdriver, player_name: str, pbp: str, include_two: bool = True
) -> dict[str, list[str]]:
    """
    Gets quarter and time of free throws for a player.
    """
    driver.get(pbp)

    play_by_play = driver.find_element(
        By.CSS_SELECTOR, ".Card.Card--PlayByPlay"
    )
    nav_bar = play_by_play.find_element(
        By.TAG_NAME, "nav"
    )
    quarters = nav_bar.find_elements(
        By.TAG_NAME, "li"
    )

    times = {}
    for quarter in quarters:
        quarter_name = "Q" + quarter.text[0]
        if quarter.text == "OT":
            quarter_name = "OT1"
        elif "OT" in quarter.text:
            quarter_name = "OT" + quarter.text[0]

        button = quarter.find_element(By.TAG_NAME, "button")
        driver.execute_script("arguments[0].click();", button)

        rows = play_by_play.find_elements(By.TAG_NAME, "tr")
        rows = rows[1:]
        for i in range(1, len(rows)):
            row_text = rows[i].text
            condition = "free throw 1 of 3" in row_text or \
                "free throw flagrant 1 of 3" in row_text
            if include_two:
                condition = "free throw 1" in row_text or \
                    "free throw flagrant 1" in row_text or \
                    "technical free throw" in row_text
            if condition and player_name in row_text:
                if quarter_name not in times:
                    times[quarter_name] = []
                time = row_text.split(maxsplit=1)[0]
                if "." in time:
                    rounded_time = round(float(time))
                    if rounded_time < 10:
                        time = "0:0" + str(rounded_time)
                    else:
                        time = "0:" + str(rounded_time)
                times[quarter_name].append(time)

    return times


def get_foul_urls(driver: webdriver, player_name: str, pbp: str, url: str) -> \
        list[tuple[str, str]]:
    """
    Parses play by play for player fouls.

    Returns list of player foul link and quarter.
    """
    if player_name == "Hansen Yang":
        player_name == "Yang Hansen"

    player_name = unidecode(player_name)

    times = _get_foul_times(driver, player_name, pbp)

    last_name = player_name.split()[-1]

    video_urls = []

    for quarter, fouls in times.items():
        driver.get(url + quarter)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

        while "content unavailable" in body:
            driver.refresh()
            body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "OT" in quarter:
            quarter = str(4 + int(quarter.lstrip("OT")))
        else:
            quarter = quarter[1]
        play_by_play = driver.find_element(By.ID, "playByPlayContainer")
        rows = play_by_play.find_elements(By.TAG_NAME, "article")
        for row in rows:
            time = row.find_element(By.XPATH, time_tag).text
            if time.startswith("0"):
                time = time[1:]
            if time == fouls[0]:
                event_text = row.text
                if ".FOUL" in event_text and last_name in event_text:
                    try:
                        event = row.find_element(
                            By.TAG_NAME, "a"
                        ).get_attribute("href")
                        video_urls.append((event, quarter))
                    except Exception:
                        pass
                    fouls.pop(0)
                    if len(fouls) == 0:
                        break

    return video_urls


def _get_foul_times(driver: webdriver, player_name: str, pbp: str) -> dict[str, list[str]]:
    """
    Gets quarter and time of foul for a player.
    """
    driver.get(pbp)

    play_by_play = driver.find_element(
        By.CSS_SELECTOR, ".Card.Card--PlayByPlay"
    )
    nav_bar = play_by_play.find_element(
        By.TAG_NAME, "nav"
    )
    quarters = nav_bar.find_elements(
        By.TAG_NAME, "li"
    )

    times = {}
    for quarter in quarters:
        quarter_name = "Q" + quarter.text[0]
        if quarter.text == "OT":
            quarter_name = "OT1"
        elif "OT" in quarter.text:
            quarter_name = "OT" + quarter.text[0]

        button = quarter.find_element(By.TAG_NAME, "button")
        driver.execute_script("arguments[0].click();", button)

        rows = play_by_play.find_elements(By.TAG_NAME, "tr")
        rows = rows[1:]
        for i in range(1, len(rows)):
            row_text = rows[i].text
            if player_name in row_text and "foul" in row_text:
                if quarter_name not in times:
                    times[quarter_name] = []
                time = row_text.split(maxsplit=1)[0]
                if "." in time:
                    rounded_time = round(float(time))
                    if rounded_time < 10:
                        time = "0:0" + str(rounded_time)
                    else:
                        time = "0:" + str(rounded_time)
                times[quarter_name].append(time)

    return times


def time_to_secs(time: str) -> int:
    split_time = time.split(":")
    minutes = int(split_time[0])
    seconds = split_time[1]
    if seconds.startswith("0"):
        seconds = seconds[1]
    seconds = int(seconds)
    return minutes * 60 + seconds
