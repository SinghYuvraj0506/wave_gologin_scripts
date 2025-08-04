import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.HumanTypingBehavior import HumanTypingBehavior
from utils.basicHelpers import getTOTP
from config import Config

def handle_two_factor_authentication(driver):
    """
    Handles the two-factor authentication step during Instagram login.

    Args:
        driver: An instance of a Selenium WebDriver.

    Returns:
        bool: True if 2FA is handled successfully or not required, False otherwise.
    """
    try:
        # Wait a moment to see if the 2FA page loads
        human_mouse = HumanMouseBehavior(driver)
        human_typing = HumanTypingBehavior(driver)

        WebDriverWait(driver, 5).until(
            EC.url_contains("two_factor")
        )
        
        print("ℹ️ Two-factor authentication required.")

        # Get the 2FA code from an environment variable
        verification_code = getTOTP(Config.INSTA_SECRET_CODE)
        
        if not verification_code:
            print("❌ Error: Generating TOTP.")
            return False

        # Find the verification code input field
        code_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-describedby='verificationCodeDescription']"))
        )

        print("TOTP is", verification_code)

        time.sleep(8)
        human_mouse.human_like_move_to_element(code_input,click=True)
        human_typing.human_like_type(code_input, verification_code)

        time.sleep(2)

        confirm_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Confirm')]"))
        )

        human_mouse.human_like_move_to_element(confirm_button,click=True)
        print("✅ 2FA code submitted successfully.")
        return True

    except TimeoutException:
        # This is not an error, it simply means the 2FA page didn't appear
        print("ℹ️ 2FA not required for this session.")
        return True
    except NoSuchElementException as e:
        print(f"❌ Error: Could not find a required element on the 2FA page.")
        print(f"Details: {e}")
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred during 2FA handling: {e}")
        return False