import os
import time
import base64
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def download_plays(driver: webdriver, base_name: str, result: list):
    i = 0
    player_urls = []
    
    # Ensure the download directory exists
    os.makedirs(os.path.abspath(base_name), exist_ok=True)

    for video_url, desc_raw, _, _ in result:
        driver.get(video_url)

        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        while "content unavailable" in body or "no video available" in body:
            driver.refresh()
            body = driver.find_element(By.TAG_NAME, "body").text.lower()

        if i == 0:
            try:
                driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Close"]').click()
            except:
                pass

        while True:
            try:
                video = WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "video.vjs-tech"))
                )
                break
            except Exception:
                driver.refresh()
                
        driver.execute_script("arguments[0].pause();", video)
        src = video.get_attribute("src")
        
        try:   
            driver.find_element(By.CSS_SELECTOR, 'button[data-click="close"]').click()
        except Exception:
            pass

        if not src.endswith("missing.mp4"):
            # Clean up the URL to construct a proper filename
            clip_name = src.split("/")[-1].split("?")[0]
            if not clip_name.endswith(".mp4"):
                clip_name = f"video_{i}.mp4"

            save_path = os.path.join(os.path.abspath(base_name), clip_name)

            # JavaScript injection script to pull down video bytes via active browser session
            js_download_script = """
            var url = arguments[0];
            var callback = arguments[arguments.length - 1];
            
            fetch(url)
                .then(response => response.blob())
                .then(blob => {
                    var reader = new FileReader();
                    reader.onloadend = function() {
                        // Extract base64 encoded data string from the data URL
                        var base64data = reader.result.split(',')[1];
                        callback(base64data);
                    }
                    reader.readAsDataURL(blob);
                })
                .catch(err => callback("ERROR: " + err));
            """

            while True:
                try:
                    print(f"Downloading clip {i} via browser fetch: {clip_name}...")
                    
                    # Execute async JS script to grab video blob as base64 string
                    base64_video_data = driver.execute_async_script(js_download_script, src)
                    
                    if base64_video_data.startswith("ERROR"):
                        print(f"JavaScript Fetch failed: {base64_video_data}")
                    else:
                        # Decode the raw base64 data and write it directly to the local disk file
                        with open(save_path, "wb") as f:
                            f.write(base64.b64decode(base64_video_data))
                        
                        player_urls.append((save_path, desc_raw))
                        i += 1
                    
                    break
    
                except:
                    pass
                
            time.sleep(1)

    return player_urls

