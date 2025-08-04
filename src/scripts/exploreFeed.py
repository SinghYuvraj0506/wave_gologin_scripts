import time
import random
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from utils.scrappingHelpers import simulate_human_scrolling

def explore_feed(driver):
    print("🏠 Visiting Instagram Home Feed...")
    driver.get("https://www.instagram.com/")
    time.sleep(5)

    print("🔽 Scrolling down the feed...")
    simulate_human_scrolling(driver, scroll_count=random.randint(6, 9), scroll_distance=600, scroll_pause=2.5)

    print("🔼 Scrolling back up the feed...")
    simulate_human_scrolling(driver, scroll_count=random.randint(3, 5), scroll_distance=600, scroll_pause=2)


def view_stories(driver, max_stories=3):
    print("📚 Looking for stories using refined selector...")

    try:
        # Wait for home to load
        time.sleep(4)

        # Find story elements with: li > span[role="link"] + img
        story_candidates = driver.find_elements(By.CSS_SELECTOR, "li > span[role='link'] + img")

        if not story_candidates:
            print("❌ No story thumbnails matched.")
            return

        print(f"🎥 Found {len(story_candidates)} story candidates.")

        # Go back to span[role=link] (previous sibling)
        first_story_span = driver.find_element(By.CSS_SELECTOR, "li > span[role='link']")
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", first_story_span)
        time.sleep(1.5)

        print("🖱️ Clicking on the first story...")
        first_story_span.click()
        time.sleep(3)

        for i in range(max_stories):
            wait_time = random.uniform(4, 7)
            print(f"👀 Viewing story {i+1}/{max_stories} for {round(wait_time, 2)}s...")
            time.sleep(wait_time)

            # Move to next story
            ActionChains(driver).send_keys(Keys.ARROW_RIGHT).perform()
            time.sleep(1)

    except Exception as e:
        print(f"⚠️ Error while viewing stories: {e}")

    finally:
        # Press ESC to exit stories
        print("🛑 Exiting stories...")
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(2)
