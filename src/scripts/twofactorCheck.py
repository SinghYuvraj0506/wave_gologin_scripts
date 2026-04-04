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
    

def _detect_2fa_ui_version(driver) -> str:
    """
    Detects which Instagram 2FA UI version is active.

    Returns:
        'new'  — new UI  (/accounts/login/two_step_verification)
        'old'  — old UI  (/accounts/login/two_factor)
        'none' — no 2FA page detected
    """
    current_url = driver.current_url
    if "two_step_verification" in current_url:
        return "new"
    if "two_factor" in current_url:
        return "old"
    return "none"


def _handle_old_2fa(driver, verification_code: str, human_mouse, human_typing, webhook) -> bool:
    """Handles the legacy Instagram 2FA UI (url contains 'two_factor')."""

    code_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[aria-describedby='verificationCodeDescription']")
        )
    )

    print("TOTP is", verification_code)
    time.sleep(8)
    human_mouse.human_like_move_to_element(code_input, click=True)
    human_typing.human_like_type(code_input, verification_code)
    time.sleep(2)

    confirm_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(text(), 'Confirm')]")
        )
    )
    human_mouse.human_like_move_to_element(confirm_button, click=True)
    time.sleep(8)

    # Check for error alert
    try:
        error_element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "twoFactorErrorAlert"))
        )
        if error_element and error_element.is_displayed():
            webhook.update_account_status("wrong_login_data", {
                "account_id": webhook.account_id,
                "profile_id": webhook.profile_id,
                "error_type": "SECRET",
            })
            raise RuntimeError("❌ Invalid 2FA code detected (Instagram rejected it).")
    except TimeoutException:
        pass  # No error → success

    print("✅ [Old UI] 2FA code submitted successfully.")
    return True


def _find_new_ui_code_input(driver):
    """
    Locates the code input field in the new 2FA UI.

    Strategy: find the <label> whose text is "Code", then return
    its immediately preceding sibling <input>.
    Falls back to a direct input[type=text/tel/number] search.
    """
    # Primary: preceding-sibling of label[text='Code']
    try:
        code_input = driver.find_element(
            By.XPATH,
            "//label[normalize-space(text())='Code']/preceding-sibling::input[1]"
        )
        return code_input
    except NoSuchElementException:
        pass

    # Fallback: any visible input near a "Code" label (broader selector)
    try:
        code_input = driver.find_element(
            By.XPATH,
            "//label[contains(translate(normalize-space(text()),'CODE','code'),'code')]"
            "/preceding-sibling::input[1]"
        )
        return code_input
    except NoSuchElementException:
        pass

    return None


def _wait_for_continue_button_enabled(driver, timeout: int = 15):
    """
    Finds the 'Continue' button by locating the span with 'Continue' text first,
    then traversing up to the ancestor div[role='button'], and waits until
    it's not aria-disabled.
    """
    def _is_enabled(drv):
        try:
            # Find the span containing 'Continue' text first
            span = drv.find_element(
                By.XPATH,
                "//span[contains(text(),'Continue')]"
            )
            # Traverse up to the ancestor div with role="button"
            btn = span.find_element(
                By.XPATH,
                "./ancestor::div[@role='button'][1]"
            )
            disabled = btn.get_attribute("aria-disabled")
            if disabled == "true":
                return False
            return btn
        except NoSuchElementException:
            return False

    return WebDriverWait(driver, timeout).until(_is_enabled)


def _handle_new_2fa(driver, verification_code: str, human_mouse, human_typing, webhook) -> bool:
    """Handles the new Instagram 2FA UI (url contains 'two_step_verification')."""

    # Wait for the code input to appear
    WebDriverWait(driver, 10).until(
        lambda d: _find_new_ui_code_input(d) is not None
    )
    code_input = _find_new_ui_code_input(driver)

    if not code_input:
        raise NoSuchElementException("Could not locate the code input on the new 2FA UI.")

    print("TOTP is", verification_code)
    time.sleep(8)
    human_mouse.human_like_move_to_element(code_input, click=True)
    human_typing.human_like_type(code_input, verification_code)
    time.sleep(2)

    # Wait until the Continue button is no longer aria-disabled
    print("⏳ Waiting for Continue button to become enabled…")
    try:
        continue_button = _wait_for_continue_button_enabled(driver, timeout=15)
    except TimeoutException:
        raise RuntimeError("❌ 'Continue' button never became enabled on the new 2FA UI.")

    human_mouse.human_like_move_to_element(continue_button, click=True)
    time.sleep(8)

    # Check for error: any span containing "please" AND "try again" (case-insensitive)
    try:
        error_span = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'please') "
                "and contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'check')"
                "and contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'code')]"
            ))
        )
        if error_span and error_span.is_displayed():
            webhook.update_account_status("wrong_login_data", {
                "account_id": webhook.account_id,
                "profile_id": webhook.profile_id,
                "error_type": "SECRET",
            })
            raise RuntimeError(f"❌ 2FA failed — Instagram said: '{error_span.text}'")
    except TimeoutException:
        pass  # No error span → success

    print("✅ [New UI] 2FA code submitted successfully.")
    return True


def handle_two_factor_authentication(driver, secret_key: str, webhook: WebhookUtils):
    """
    Handles the two-factor authentication step during Instagram login.
    Automatically detects and supports both the old UI (two_factor) and
    the new UI (two_step_verification). Returns True immediately if no
    2FA page is detected.
    """
    try:
        human_mouse = HumanMouseBehavior(driver)
        human_typing = HumanTypingBehavior(driver)

        # Wait briefly to detect which 2FA UI loaded (if any)
        try:
            WebDriverWait(driver, 5).until(
                lambda d: _detect_2fa_ui_version(d) != "none"
            )
        except TimeoutException:
            # No 2FA page appeared at all — not required
            print("ℹ️ 2FA not required for this session.")
            return True

        ui_version = _detect_2fa_ui_version(driver)

        # Double-check: if somehow still 'none', treat as not required
        if ui_version == "none":
            print("ℹ️ 2FA page not found, skipping.")
            return True

        print(f"ℹ️ Two-factor authentication required. Detected UI: {ui_version}")

        # Validate secret before doing anything
        if not secret_key or not is_valid_totp_secret(secret_key):
            webhook.update_account_status("wrong_login_data", {
                "account_id": webhook.account_id,
                "profile_id": webhook.profile_id,
                "error_type": "SECRET",
            })
            raise RuntimeError("❌ Invalid TOTP secret key provided.")

        verification_code = getTOTP(secret_key)
        if not verification_code:
            print("❌ Error: Generating TOTP.")
            return False

        if ui_version == "new":
            return _handle_new_2fa(driver, verification_code, human_mouse, human_typing, webhook)
        else:
            return _handle_old_2fa(driver, verification_code, human_mouse, human_typing, webhook)

    except TimeoutException as e:
        print(f"TimeoutException Details: {e}")
        print("ℹ️ 2FA not required for this session.")
        return True
    except NoSuchElementException as e:
        print(f"❌ Error: Could not find a required element on the 2FA page.\nDetails: {e}")
        return False
    except RuntimeError:
        raise
    except Exception as e:
        print(f"❌ An unexpected error occurred during 2FA handling: {e}")
        return False