from selenium import webdriver
from selenium.webdriver.common.by import By
import math
from unidecode import unidecode


box_score_tag = '//table[starts-with(@class, "StatsTable_table")]'
name_tag = './/span[@class = "GameBoxscoreTablePlayer_gbpNameFull__cf_sn"]'
time_tag = ".//span[starts-with(@class, 'GamePlayByPlayRow_clockElement')]"


def get_player_urls(
    player_name: str, box_score: str, td_vals: list[int]
) -> list[tuple[int, str]]:
    """
    Parses box score for player event links.

    Returns list of player event (int) and link.
    
    Example: [("3", link to fg made), ("14", link to reb)]
    """
    driver = webdriver.Chrome()

    driver.get(box_score)
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
            except Exception:
                pass

    driver.close()

    return urls


def get_ft_urls(
    player_name: str, pbp: str, url: str, include_two: bool = True
) -> list[tuple[str, str]]:
    """
    Parses play by play for player free throw links.

    Returns list of player free throw link and quarter.
    """
    player_name = unidecode(player_name)

    times = _get_ft_times(player_name, pbp, include_two)

    last_name = player_name.split()[-1]

    driver = webdriver.Chrome()
    driver.implicitly_wait(60)

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

    driver.close()

    return video_urls


def _get_ft_times(
    player_name: str, pbp: str, include_two: bool = True
) -> dict[str, list[str]]:
    """
    Gets quarter and time of free throws for a player.
    """
    driver = webdriver.Chrome()
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
                    time = "0:" + str(math.ceil(float(time)))
                times[quarter_name].append(time)

    driver.close()

    return times


def get_foul_urls(player_name: str, pbp: str, url: str) -> \
        list[tuple[str, str]]:
    """
    Parses play by play for player fouls.

    Returns list of player foul link and quarter.
    """
    player_name = unidecode(player_name)

    times = _get_foul_times(player_name, pbp)

    last_name = player_name.split()[-1]

    driver = webdriver.Chrome()
    driver.implicitly_wait(60)

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

    driver.close()

    return video_urls


def _get_foul_times(player_name: str, pbp: str) -> dict[str, list[str]]:
    """
    Gets quarter and time of foul for a player.
    """
    driver = webdriver.Chrome()
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
                    time = "0:" + str(math.ceil(float(time)))
                times[quarter_name].append(time)

    driver.close()

    return times


def time_to_secs(time: str) -> int:
    split_time = time.split(":")
    minutes = int(split_time[0])
    seconds = split_time[1]
    if seconds.startswith("0"):
        seconds = seconds[1]
    seconds = int(seconds)
    return minutes * 60 + seconds
