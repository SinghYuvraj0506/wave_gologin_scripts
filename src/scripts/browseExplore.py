import time
import random
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.BasicUtils import BasicUtils
from utils.scrapping.ScreenObserver import ScreenObserver

def browse_explore_page(driver,observer: ScreenObserver):
    basicUtils = BasicUtils(driver)
    human_mouse = HumanMouseBehavior(driver)
    observer.health_monitor.revive_driver("click_body")
    human_mouse.random_mouse_jitter(duration=5)

    try:
        print("🧭 Navigating to Instagram Explore Page...")
        basicUtils.click_anchor_by_href("/explore/")

        observer.health_monitor.revive_driver("screenshot")
        
        time.sleep(5)
        human_mouse.random_mouse_jitter(duration=2)
        human_mouse.natural_scroll(direction="down", amount=random.randint(200, 600))
        human_mouse.random_mouse_jitter(duration=2)

        observer.health_monitor.revive_driver("scroll")

        # Find the main content area
        main_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "main[role='main']"))
        )

        post_links = main_element.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
        print(f"🖼️ Found {len(post_links)} explore posts.")

        # Step 3: Pick random 2–5 to view
        to_view = random.sample(post_links, min(len(post_links), random.randint(2, 5)))

        for i, post in enumerate(to_view):
            try:
                print(f"\n🔍 Opening post {i+1}/{len(to_view)}")

                # Scroll the post into view
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", post)
                time.sleep(random.uniform(0.5, 1.5))

                # Click to open
                post.click()
                time.sleep(random.uniform(2.5, 4.5))  # Simulate reading/viewing
                human_mouse.random_mouse_jitter(duration=2)

                if i % 2 == 0: 
                    observer.health_monitor.revive_driver("screenshot")

                print("🔙 Going back to explore")
                driver.back()
                time.sleep(random.uniform(2.5, 4))

                # Scroll again after viewing a post
                observer.health_monitor.revive_driver("scroll")
                human_mouse.random_mouse_jitter(duration=2)
                human_mouse.natural_scroll(direction="down", amount=random.randint(200, 600))

            except Exception as e:
                print(f"⚠️ Failed to open/view post: {e}")
                driver.back()
                time.sleep(2)

        observer.health_monitor.revive_driver("screenshot")

    except NoSuchElementException or TimeoutException:
        print("❌ No posts found on explore page.")

    print("🏠 Returning to Instagram home page.")
    driver.get("https://www.instagram.com/")
