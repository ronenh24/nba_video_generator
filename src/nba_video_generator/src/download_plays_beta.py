import os
import time
import pyautogui
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def download_plays(driver: webdriver, base_name: str, result: list):
    i = 0
    player_urls = []
    for video_url, desc_raw, _, _ in result:
        driver.get(video_url)

        body = driver.find_element(By.TAG_NAME, "body").text.lower()

        while "content unavailable" in body or \
                "no video available" in body:
            driver.refresh()
            body = driver.find_element(By.TAG_NAME, "body").text.lower()

        if i == 0:
            try:
                driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Close"]').click()
            except:
                pass

        video_path = os.path.join(os.path.abspath(base_name), "temp" + str(i) + ".mp4") if i == 0 else "temp" + str(i) + ".mp4"

        video = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "video.vjs-tech"))
        )
        src = video.get_attribute("src")
        
        try:   
            driver.find_element(By.CSS_SELECTOR, 'button[data-click="close"]').click()
        except:
            pass

        if not src.endswith("missing.mp4"): 
            ActionChains(driver).move_to_element(video).context_click(video).perform()
            time.sleep(3)
            pyautogui.typewrite(['down', 'down', 'down', 'down', 'down', 'enter']) 
            time.sleep(3)
            pyautogui.write(video_path, interval=0.20)
            pyautogui.press('enter')
            player_urls.append((os.path.join(os.path.abspath(base_name), "temp" + str(i) + ".mp4"), desc_raw))
            i += 1

    return player_urls
