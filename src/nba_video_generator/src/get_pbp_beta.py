from selenium import webdriver
from selenium.webdriver.common.by import By


boxscore_tag = "//a[@data-text='BOX SCORE']"


def get_pbp(driver: webdriver, base_url: str, date: str, team: str):
    driver.get(base_url + date)

    body = driver.find_element(By.TAG_NAME, "body").text.lower()

    while "content unavailable" in body:
        driver.refresh()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

    box_score_url = ""

    game_urls = driver.find_elements(By.XPATH, boxscore_tag)

    for game_url in game_urls:
        game_url = game_url.get_attribute("href")
        if team in game_url:
            box_score_url = game_url

    if box_score_url == "":
        return None, None

    home_away = box_score_url.split("vs")[1]

    if team in home_away:
        data_is_home_team = "true"
    else:
        data_is_home_team = "false"

    pbp_url = box_score_url.rsplit("/", 1)[0] + "/play-by-play"

    return data_is_home_team, pbp_url
