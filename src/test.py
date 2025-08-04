from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
from gologin import GoLogin
import sys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scripts.exploreReel import explore_reels_randomly
from scripts.browseExplore import browse_explore_page
from scripts.goToMessages import search_and_message_users
from utils.basicHelpers import get_ip_proxy


def main():
    try:
        params = {
            'token': "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2ODUzMDNhMGUyNDczOGUyOGVjOWNhZWEiLCJ0eXBlIjoiZGV2Iiwiand0aWQiOiI2ODZiNDg2ODg0YTEzYjdkOTUxNWFkODkifQ.CefiYpRiCocixtheKySboexl-q8lSPe63r45BTN1Y30",
            'extra_params': [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-gpu-sandbox',

                # VULKAN-SPECIFIC FIXES
                '--disable-vulkan',
                '--disable-vulkan-surface',
                '--disable-vulkan-fallback-to-gl-for-testing',
                '--use-vulkan=disabled',

                # FORCE SOFTWARE RENDERING
                '--use-gl=disabled',
                '--disable-accelerated-2d-canvas',
                '--disable-accelerated-video-decode',
                '--disable-gpu-rasterization',
                '--disable-gpu-memory-buffer-video-frames',

                # DISABLE PROBLEMATIC FEATURES
                '--disable-features=VizDisplayCompositor,Vulkan,UseSkiaRenderer,WebGL,WebGL2',
                '--disable-3d-apis',
                '--disable-webgl',
                '--disable-webgl2',

                # YOUR EXISTING FLAGS
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-blink-features=AutomationControlled',
                '--window-size=1920,1080'
            ]
        }
        gologin = GoLogin(params)
        profile_id = "687e4c10ef91c2c4838ab98d"
        gologin.setProfileId(profile_id)
        debugger_address = gologin.start()

        print("debugger Address", debugger_address)

        service = Service(ChromeDriverManager(
            driver_version=gologin.get_chromium_version()).install())
        chrome_options = Options()
        chrome_options.add_experimental_option(
            "debuggerAddress", debugger_address)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        print("Checkign proxy data----------")
        get_ip_proxy(driver)
        time.sleep(1)

        driver.execute_script("window.scrollTo(0, 100);")
        time.sleep(2)

        driver.get("https://www.instagram.com/")
        print("Visited insta---------")
        time.sleep(3)

        driver.execute_script("window.scrollTo(0, 100);")

        try:
            explore_reels_randomly(driver)

            # time.sleep(8)

            # browse_explore_page(driver)

            search_and_message_users(
                driver, 
                usernames_list=["ssinghyuvraj02", "khushiie2005"],
                message_text="Hello , kya kar rhe ho"
            )


        except Exception as e:
            print("❌ Error in checking insta:", e)

        driver.save_screenshot("/app/instagram_0.png")

        time.sleep(20)
        driver.quit()

        gologin.stop()

    except Exception as e:
        print('❌ Error', e)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'❌ {e}')
        sys.exit(1)
