import time
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.scrapping.BasicUtils import BasicUtils
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.ScreenObserver import ScreenObserver
from utils.WebhookUtils import WebhookUtils

def goto_profile_and_save_image (driver, observer: ScreenObserver, username:str, webhook:WebhookUtils):
    """
    Navigate to an Instagram profile and save profile image.

    Args:
        driver: Selenium WebDriver instance
        observer: ScreenObserver instance for monitoring
        username: Instagram handle to visit
        max_images: Max number of profile images to save
    """
     
    basicUtils = BasicUtils(driver)
    human_mouse = HumanMouseBehavior(driver)
    observer.health_monitor.revive_driver("click_body")
    human_mouse.random_mouse_jitter(duration=5)
    
    try:
        print("🎬 Navigating to User Profile...")
        basicUtils.click_anchor_by_href(f"/{username}/")

        observer.health_monitor.revive_driver("screenshot")

        time.sleep(6)

        # Wait for Profile image feed to load
        element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, f"//img[contains(@alt, \"{username}'s profile picture\")]"))
        )

        print("✅ Profile page loaded.")
        time.sleep(3)

        img_url = element.get_attribute("src")
        print(f"🖼️ Profile image URL: {img_url}")

        # Sending webhook to server to save the profile image
        try:
            webhook.update_account_status(event="update_profile_image",payload={
                "account_id": webhook.account_id,
                "profile_url":img_url
            })
        except Exception as e:
            print("Error sending image to server", str(e))

    except TimeoutException:
        print("❌ Timeout: Profile image did not load.")
        driver.get("https://www.instagram.com/")
        return

