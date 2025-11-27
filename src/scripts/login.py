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

        try:
            login_form_old = driver.find_elements(By.CSS_SELECTOR, "form#loginForm")
            login_form_new = driver.find_elements(By.CSS_SELECTOR, "form#login_form")

            if login_form_new:
                print("🔄 New login page detected!")

                username_selector = (By.NAME, "email")
                password_selector = (By.NAME, "pass")
                login_button_xpath = "//div[@role='button' and contains(., 'Log in')]"

            else:
                print("🟦 Classic Instagram login page detected")

                username_selector = (By.NAME, "username")
                password_selector = (By.NAME, "password")
                login_button_xpath = "//button[contains(., 'Log in')]"

        except Exception as e:
            print("❌ Failed detecting login form:", e)
            return False

        username_input = wait.until(
            EC.presence_of_element_located(username_selector)
        )
        password_input = wait.until(
            EC.presence_of_element_located(password_selector)
        )

        human_mouse.human_like_move_to_element(username_input, click=True)
        human_typing.human_like_type(
            username_input, text=username, typing_speed="normal")

        time.sleep(2)

        human_mouse.human_like_move_to_element(password_input, click=True)
        human_typing.human_like_type(
            password_input, text=password, typing_speed="slow", raw_mode=True)

        time.sleep(3)

        # ✅ Check if the "Log in" button is disabled before proceeding
        try:
            login_button = wait.until(
                EC.presence_of_all_elements_located((By.XPATH, login_button_xpath))
            )[0]
            is_disabled = (
                login_button.get_attribute("disabled")
                or login_button.get_attribute("aria-disabled") == "true"
            )


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

        password_input.send_keys(Keys.RETURN)

        # ⏳ wait briefly for potential error
        time.sleep(8)
        keywords = ["incorrect", "sorry", "double-check", "credentials"]

        # Only look inside <span> tags that might show login errors
        xpath_cond = " or ".join(
            f"contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{kw}')"
            for kw in keywords
        )
        error_xpath = f"//span[{xpath_cond}]"

        try:
            # Wait up to 5s for any matching <span> with those words
            error_elem = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.XPATH, error_xpath))
            )

            time.sleep(0.3)  # debounce in case of transient UI
            text = error_elem.text.strip().lower()
            print(f"⚠️ Found potential login error text: {text}")

            if any(k in text for k in keywords):
                webhook.update_account_status("wrong_login_data", {
                    "account_id": webhook.account_id,
                    "profile_id": webhook.profile_id,
                    "error_type": "CREDENTIALS"
                })
                raise RuntimeError(f"❌ Invalid credentials detected: {text}")
            else:
                print("ℹ️ Found span, but message not credential-related — continuing login flow.")

        except TimeoutException:
            # No visible span with these words — normal flow
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
