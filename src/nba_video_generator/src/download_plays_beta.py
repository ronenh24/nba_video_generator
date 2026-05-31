import os
import time
import pyautogui
import pyperclip
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

        # video_path = os.path.join(os.path.abspath(base_name), str(i) + ".mp4") if i == 0 else str(i)

        video = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "video.vjs-tech"))
        )
        driver.execute_script("arguments[0].pause();", video)
        src = video.get_attribute("src")
        
        try:   
            driver.find_element(By.CSS_SELECTOR, 'button[data-click="close"]').click()
        except:
            pass

        if not src.endswith("missing.mp4"):
            ActionChains(driver).pause(3).move_to_element(video).context_click(video).perform()
            time.sleep(1)
            pyautogui.typewrite(['down', 'down', 'down', 'down', 'down', 'enter']) 
            time.sleep(3)
            pyautogui.hotkey('ctrl', 'c')
            clip_name = pyperclip.paste()
            if i == 0:
                pyautogui.write(os.path.join(os.path.abspath(base_name), clip_name + ".mp4"), interval=0.10)
            pyautogui.press('enter')
            player_urls.append((os.path.join(os.path.abspath(base_name), clip_name + ".mp4"), desc_raw))
            i += 1

    return player_urls
