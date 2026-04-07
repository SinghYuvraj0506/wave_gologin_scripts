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
        time.sleep(6)

        # ── Extract image src from DOM attribute (no image request needed) ─
        # The src attribute is written into the HTML by Instagram's SSR/JS
        # even when the actual image request is blocked by the browser.
        img_url = None
        elements = driver.find_elements(
            By.XPATH,
            f"//img[contains(@alt, \"{username}'s profile picture\")]"
        )

        if elements:
            src = elements[0].get_attribute("src")
            if src and src.startswith("http"):
                img_url = src
                print(f"🖼️ Profile image URL: {img_url}")

        else:
            elements = driver.find_elements(
                By.XPATH,
                "//img[contains(@alt, 'Change profile photo')]"
            )
            if elements:
                src = elements[0].get_attribute("src")
                if src and src.startswith("http"):
                    img_url = src
                    print(f"🖼️ Profile image URL: {img_url}")

        if img_url is not None:
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
            print("❌ Profile image not found.")
            
    except TimeoutException:
        print("❌ Timeout: Profile page URL did not load.")
        try:
            basicUtils.click_anchor_by_href("https://www.instagram.com")
        except Exception as e:
            print("Error returning to home page", str(e))
            driver.get("https://www.instagram.com/")