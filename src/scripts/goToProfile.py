import time
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.scrapping.BasicUtils import BasicUtils
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.ScreenObserver import ScreenObserver
from utils.WebhookUtils import WebhookUtils


def goto_profile_and_save_image(driver, observer: ScreenObserver, username: str, webhook: WebhookUtils):
    """
    Navigate to an Instagram profile and save profile image.
    Works with bandwidth saver / image-blocking enabled — does NOT wait
    for the <img> element to load. Instead waits for the profile URL to
    settle and extracts the image src from the DOM (which is present in
    the HTML even when the image request itself is blocked).
    """

    basicUtils = BasicUtils(driver)
    human_mouse = HumanMouseBehavior(driver)
    observer.health_monitor.revive_driver("click_body")
    human_mouse.random_mouse_jitter(duration=5)

    try:
        print("🎬 Navigating to User Profile...")
        basicUtils.click_anchor_by_href(f"/{username}/")
        observer.health_monitor.revive_driver("screenshot")

        # ── Wait for the URL to land on the profile page ──────────────────
        # We don't care whether images loaded; we just need the page HTML.
        WebDriverWait(driver, 20).until(
            EC.url_contains(f"/{username}/")
        )
        print("✅ Profile page URL confirmed.")

        # Give the DOM a moment to populate (no image load needed)
        time.sleep(3)

        # ── Extract image src from DOM attribute (no image request needed) ─
        # The src attribute is written into the HTML by Instagram's SSR/JS
        # even when the actual image request is blocked by the browser.
        img_url = None
        try:
            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    f"//img[contains(@alt, \"{username}'s profile picture\")]"
                ))
            )
            img_url = element.get_attribute("src")
        except TimeoutException:
            # Image element not in DOM (e.g. fully blocked) — fall back to
            # scraping the raw page source for the src URL
            print("⚠️ Image element not found in DOM, scanning page source...")
            page_source = driver.page_source
            marker = f"{username}&#039;s profile picture"
            alt_marker = f"{username}'s profile picture"
            for src_marker in [marker, alt_marker]:
                idx = page_source.find(src_marker)
                if idx != -1:
                    # Walk back to find the nearest src="..."
                    chunk = page_source[max(0, idx - 500):idx]
                    src_start = chunk.rfind('src="')
                    if src_start != -1:
                        src_end = chunk.find('"', src_start + 5)
                        img_url = chunk[src_start + 5:src_end]
                        break

        if img_url:
            print(f"🖼️ Profile image URL: {img_url}")
            try:
                webhook.update_account_status(
                    event="update_profile_image",
                    payload={
                        "account_id": webhook.account_id,
                        "profile_url": img_url,
                    }
                )
            except Exception as e:
                print("Error sending image to server", str(e))
        else:
            print("⚠️ Could not extract profile image URL — sending without it.")
            # Still report success so the caller isn't blocked
            try:
                webhook.update_account_status(
                    event="update_profile_image",
                    payload={
                        "account_id": webhook.account_id,
                        "profile_url": None,
                    }
                )
            except Exception as e:
                print("Error sending status to server", str(e))

    except TimeoutException:
        print("❌ Timeout: Profile page URL did not load.")
        try:
            basicUtils.click_anchor_by_href("https://www.instagram.com")
        except Exception as e:
            print("Error returning to home page", str(e))
            driver.get("https://www.instagram.com/")