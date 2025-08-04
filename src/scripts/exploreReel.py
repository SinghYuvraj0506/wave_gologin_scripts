import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.scrapping.BasicUtils import BasicUtils
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.ScreenObserver import ScreenObserver

def explore_reels_randomly(driver, observer: ScreenObserver,count=5, min_watch=4, max_watch=12):
    basicUtils = BasicUtils(driver)
    human_mouse = HumanMouseBehavior(driver)
    observer.health_monitor.revive_driver("click_body")
    human_mouse.random_mouse_jitter(duration=5)
    
    try:
        print("🎬 Navigating to Instagram Reels...")
        basicUtils.click_anchor_by_href("/reels/")

        observer.health_monitor.revive_driver("screenshot")

        # Wait for Reels feed to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "video"))
        )

        print("✅ Reels page loaded.")
    except TimeoutException:
        print("❌ Timeout: Reels did not load. Redirecting to Instagram Home.")
        driver.get("https://www.instagram.com/")
        return

    time.sleep(3)
    observer.health_monitor.revive_driver("scroll")
    human_mouse.random_mouse_jitter(duration=5)
    time.sleep(2)

    human_mouse.focus_on_screen()

    for i in range(count):
        print(f"\n▶️ Watching Reel {i+1}/{count}")
        
        # Random wait between 4 to 12 seconds
        watch_time = random.randint(min_watch, max_watch)

        # Try to grab some info
        try:
            presentation_div = driver.find_element(By.CSS_SELECTOR, "div[role='presentation']")
            creator_name = presentation_div.text.split("\n")[0].strip()
        except NoSuchElementException:
            creator_name = "Unknown Creator"


        if i % 2 == 0: 
                observer.health_monitor.revive_driver("scroll")

        print(f"📸 Creator: {creator_name}")
        print(f"⏱️ Watching for {watch_time} seconds...")
        time.sleep(watch_time)

        scroll_behavior = random.choice(["down", "up", "stay"])

        if scroll_behavior == "down":
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_DOWN)
            print("⬇️ Scrolled to next reel")
        elif scroll_behavior == "up":
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_UP)
            print("⬆️ Scrolled back to previous reel")
        else:
            print("😐 Stayed on the same reel (no scroll)")
        
        time.sleep(random.uniform(1.5, 2.5))

        # Optional check if new reel is loaded or stuck
        try:
            observer.health_monitor.revive_driver("screenshot")
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "video"))
            )
        except TimeoutException:
            print("⚠️ Reel load timeout. Returning to home feed.")
            driver.get("https://www.instagram.com/")
            return

    print("\n✅ Done exploring reels.")
    driver.get("https://www.instagram.com/")
