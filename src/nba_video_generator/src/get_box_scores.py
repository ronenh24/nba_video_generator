from selenium import webdriver
from selenium.webdriver.common.by import By


base_url = "https://www.nba.com/games?date="
boxscore_tag = "//a[@data-text='BOX SCORE']"
espn_boxscore_tag = '//section[starts-with(@class, "Scoreboard")]'
card_tag = './/a[starts-with(@class, "AnchorLink Button")]'
team_tag = './/a[@class="AnchorLink"]'
espn_url = "https://www.espn.com/nba/scoreboard/_/date/"
espn_team_abbr = {
    "gsw": "gs",
    "nop": "no",
    "nyk": "ny",
    "sas": "sa",
    "uta": "utah",
    "was": "wsh"
}


def get_box_scores(date: str, team: str) -> str:
    """
    Parses the NBA games on date and locates team box score link.
    """
    driver = webdriver.Chrome()

    driver.get(base_url + date)

    body = driver.find_element(By.TAG_NAME, "body").text.lower()

    while "content unavailable" in body:
        driver.refresh()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()

    game_urls = driver.find_elements(By.XPATH, boxscore_tag)

    for game_url in game_urls:
        game_url = game_url.get_attribute("href")
        if team in game_url:
            driver.close()
            print(game_url)
            return game_url
    driver.close()

    return None


def get_free_throws_or_fouls(date: str, team: str) -> str:
    """
    Parses ESPN NBA games on date and locates play by play link
    """
    driver = webdriver.Chrome()

    driver.get(espn_url + date.replace("-", ""))

    game_urls = driver.find_elements(By.XPATH, espn_boxscore_tag)

    for game_url in game_urls:
        if team in espn_team_abbr:
            team = espn_team_abbr[team]

        links = game_url.find_elements(By.XPATH, team_tag)
        for link in links:
            link = link.get_attribute("href")
            if link.rsplit("/", 1)[0].endswith(team):
                cards = game_url.find_elements(By.XPATH, card_tag)
                for card in cards:
                    card = card.get_attribute("href")
                    if "boxscore" in card:
                        driver.close()
                        print(card.replace("boxscore", "playbyplay"))
                        return card.replace("boxscore", "playbyplay")
    driver.close()

    return None
