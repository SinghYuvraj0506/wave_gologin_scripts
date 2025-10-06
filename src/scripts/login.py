from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.HumanTypingBehavior import HumanTypingBehavior
from scripts.twofactorCheck import handle_two_factor_authentication
import time
from utils.scrapping.ScreenObserver import ScreenObserver
from utils.WebhookUtils import WebhookUtils


def insta_login(driver, username: str, password: str, secret_key: str, observer: ScreenObserver, webhook: WebhookUtils):
    """
    Logs into Instagram using the provided Selenium driver.

    Args:
        driver: An instance of a Selenium WebDriver.

    Returns:
        bool: True if login is successful, False otherwise.
    """

    try:
        human_mouse = HumanMouseBehavior(driver)
        human_typing = HumanTypingBehavior(driver)

        driver.get("https://www.instagram.com")
        wait = WebDriverWait(driver, 15)

        observer.health_monitor.revive_driver("click_body")
        human_mouse.random_mouse_jitter(4)

        # to see the allow cookies dialog -------------------
        time.sleep(10)

        username_input = wait.until(
            EC.presence_of_element_located((By.NAME, "username")))
        password_input = wait.until(
            EC.presence_of_element_located((By.NAME, "password")))

        human_mouse.human_like_move_to_element(username_input, click=True)
        human_typing.human_like_type(
            username_input, text=username, typing_speed="normal")

        time.sleep(2)

        human_mouse.human_like_move_to_element(password_input, click=True)
        human_typing.human_like_type(
            password_input, text=password, typing_speed="slow")

        time.sleep(3)

        # ✅ Check if the "Log in" button is disabled before proceeding
        try:
            login_button = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//button[contains(., 'Log in') or @type='submit']")
            ))
            is_disabled = login_button.get_attribute("disabled")

            if is_disabled:
                webhook.update_account_status("wrong_login_data", {
                    "account_id": webhook.account_id,
                    "profile_id": webhook.profile_id,
                    "error_type": "CREDENTIALS"
                })
                raise RuntimeError(
                    "❌ Login button is disabled — invalid credentials or incomplete form")

        except TimeoutException:
            print("⚠️ Login button not found (skipping disabled check)")

        # go to click login  ---------
        human_mouse.human_like_move_to_element(element=(
            By.XPATH, "//button[contains(., 'Log in') or @type='submit']"), click=True)

        # ⏳ wait briefly for potential error
        time.sleep(8)
        try:
            error_field = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '[aria-describedby="slfErrorAlert"]'))
            )
            if error_field and error_field.is_displayed():
                msg = error_field.text.strip().lower()
                if "password" in msg or "incorrect" in msg or "username" in msg or "credentials" in msg:
                    webhook.update_account_status("wrong_login_data", {
                        "account_id": webhook.account_id,
                        "profile_id": webhook.profile_id,
                        "error_type": "CREDENTIALS"
                    })
                    raise RuntimeError(
                        "❌ Invalid credentials detected (field has aria-describedby=slfErrorAlert)")

        except TimeoutException:
            # no error field → continue login
            pass

        # Handle 2FA if required
        if not handle_two_factor_authentication(driver, secret_key=secret_key, webhook=webhook):
            return False

        time.sleep(40)
        print("✅ Login Script Execution done!")
        return True

    except TimeoutException as e:
        print("❌ Error during login: A timeout occurred.")
        print(f"Details: {e}")
        return False
    except NoSuchElementException as e:
        print("❌ Error during login: Could not find a required element.")
        print(f"Details: {e}")
        return False

    except RuntimeError:
        raise

    except Exception as e:
        print(f"❌ Unexpected error during login: {e}")
        return False
