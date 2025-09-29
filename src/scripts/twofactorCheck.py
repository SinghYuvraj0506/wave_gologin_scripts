import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.HumanTypingBehavior import HumanTypingBehavior
from utils.basicHelpers import getTOTP
from utils.WebhookUtils import WebhookUtils

def is_valid_totp_secret(secret: str) -> bool:
    """Validate if the secret is a proper base32 TOTP key."""
    try:
        # Try base32 decoding, will raise if invalid
        base64.b32decode(secret, casefold=True)
        return True
    except Exception:
        return False
    

def handle_two_factor_authentication(driver, secret_key:str, webhook:WebhookUtils):
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

        if not secret_key or not is_valid_totp_secret(secret_key):
            webhook.update_account_status("wrong_login_data",{
                    "account_id":webhook.account_id,
                    "profile_id": webhook.profile_id,
                    "error_type":"SECRET"
                })
            raise RuntimeError("❌ Invalid TOTP secret key provided.")

        # Get the 2FA code from an environment variable
        verification_code = getTOTP(secret_key)
        
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
        time.sleep(6)
        
        try:
            error_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "twoFactorErrorAlert"))
            )
            if error_element and error_element.is_displayed():
                webhook.update_account_status("wrong_login_data",{
                    "account_id":webhook.account_id,
                    "profile_id": webhook.profile_id,
                    "error_type":"SECRET"
                })
                raise RuntimeError("❌ Invalid 2FA code detected (Instagram rejected it).")
        except TimeoutException:
            # No error element appeared → success
            pass

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
    except RuntimeError:
        raise
    except Exception as e:
        print(f"❌ An unexpected error occurred during 2FA handling: {e}")
        return False