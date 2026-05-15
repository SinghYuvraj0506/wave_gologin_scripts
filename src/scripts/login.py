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
from utils.connectivityChecks import check_connectivity
from utils.exceptions import (
    UIChangeError
)

def insta_login(driver, username: str, password: str, secret_key: str, observer: ScreenObserver, webhook: WebhookUtils, proxy_config: dict):
    """
    Logs into Instagram with up to MAX_LOGIN_RETRIES internal sub-retries.

    Global attempt awareness:
      - If NOT the last global attempt: return False silently on any failure
        (no wrong_login_data or update_session webhooks — server will retry)
      - If IS the last global attempt: send appropriate failure webhooks
        so the server knows the real reason and can mark accordingly

    Args:
        global_attempt: current attempt number from server (1-indexed)
        total_attempts: total attempts server will make before giving up
    """
    attempt = webhook.attributes.get("attempt", 0)
    max_attempts = webhook.attributes.get("max_attempts", 2)

    is_last_attempt = attempt >= max_attempts

    proxy_host = proxy_config.get("host")
    proxy_port = proxy_config.get("port")
    proxy_user = proxy_config.get("username")
    proxy_pass = proxy_config.get("password")

    print(f"\n🌐 insta_login | global attempt {attempt}/{max_attempts} | last={is_last_attempt}")

    try:
        return _attempt_login(
            driver=driver,
            username=username,
            password=password,
            secret_key=secret_key,
            observer=observer,
            webhook=webhook,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_user=proxy_user,
            proxy_pass=proxy_pass,
            is_last_attempt=is_last_attempt
        )

    except (UIChangeError, RuntimeError):
        raise

    except Exception as e:
        print(f"❌ Unexpected error during login: {e}")
        return False


def _attempt_login(driver, username:str, password:str, secret_key:str, observer:ScreenObserver, webhook:WebhookUtils, proxy_host:str, proxy_port:int, proxy_user:str, proxy_pass:str, is_last_attempt: bool = False) -> bool:
    """
    Performs a single full login attempt.

    Returns:
        Bool
    """
    try:
        human_mouse = HumanMouseBehavior(driver)
        human_typing = HumanTypingBehavior(driver)

        driver.get("https://www.instagram.com")
        wait = WebDriverWait(driver, 15)

        observer.health_monitor.revive_driver("click_body")
        human_mouse.random_mouse_jitter(4)

        # Wait for cookies dialog / page to settle
        time.sleep(10)

        # ── Check for "Use another profile" button ────────────────────────────────
        try:
            use_another_profile_xpath = "//div[@role='none'][.//span[contains(., 'Use') and contains(., 'another') and contains(., 'profile')]]"
            use_another_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, use_another_profile_xpath))
            )
            print("👤 'Use another profile' button detected — clicking it...")
            human_mouse.human_like_move_to_element(use_another_btn, click=True)
            time.sleep(3)
            print("✅ Clicked 'Use another profile'")
        except TimeoutException:
            print("ℹ️ No 'Use another profile' button — proceeding normally")

        # ── Detect login form type ─────────────────────────────────────────────
        try:
            login_form_new = driver.find_elements(By.CSS_SELECTOR, "form#login_form")

            if login_form_new:
                print("🔄 New login page detected!")
                login_button_xpath = "//div[@role='button' and contains(., 'Log in')]"
            else:
                print("🟦 Classic Instagram login page detected")
                login_button_xpath = "//button[contains(., 'Log in')]"

        except Exception as e:
            print(f"❌ Failed detecting login form: {e}")
            raise UIChangeError(
                "Login form not detected",
                context={"account_username": username},
            ) from e

        # ✅ Try both selector variants for username and password fields
        username_input = None
        password_input = None

        username_selectors = [(By.NAME, "username"), (By.NAME, "email")]
        password_selectors = [(By.NAME, "password"), (By.NAME, "pass")]

        # ── Type credentials ───────────────────────────────────────────────────
        for selector in username_selectors:
            try:
                username_input = wait.until(EC.presence_of_element_located(selector))
                print(f"✅ Username field found via: {selector}")
                break
            except TimeoutException:
                continue

        for selector in password_selectors:
            try:
                password_input = wait.until(EC.presence_of_element_located(selector))
                print(f"✅ Password field found via: {selector}")
                break
            except TimeoutException:
                continue

        if not username_input or not password_input:
            raise UIChangeError(
                "❌ Login form fields not found (tried username/email and password/pass)",
                context={"account_username": username},
            )

        human_mouse.human_like_move_to_element(username_input, click=True)
        human_typing.human_like_type(username_input, text=username, typing_speed="normal")
        time.sleep(2)

        human_mouse.human_like_move_to_element(password_input, click=True)
        human_typing.human_like_type(password_input, text=password, typing_speed="slow", raw_mode=True)
        time.sleep(3)

        # ── Check login button isn't disabled ─────────────────────────────────
        try:
            login_button = wait.until(
                EC.presence_of_all_elements_located((By.XPATH, login_button_xpath))
            )[0]
            is_disabled = (
                login_button.get_attribute("disabled")
                or login_button.get_attribute("aria-disabled") == "true"
            )
            if is_disabled:
                print("❌ Login button is disabled — form incomplete or invalid")
                return False

        except TimeoutException:
            print("⚠️ Login button not found (skipping disabled check)")

        # ── Submit ─────────────────────────────────────────────────────────────
        password_input.send_keys(Keys.RETURN)

        # ✅ Wait for URL to change instead of fixed sleep
        print("⏳ Waiting for Instagram to process login...")
        login_url = driver.current_url
        try:
            WebDriverWait(driver, 20).until(lambda d: d.current_url != login_url)
            print(f"✅ URL changed to: {driver.current_url}")
        except TimeoutException:
            print("⚠️ URL did not change after 20s — checking page state...")

        time.sleep(2)

        # ── Email verification checkpoint ──────────────────────────────────────
        if not handle_email_verification_checkpoint(driver, webhook):
            print("🛑 Email verification required — stopping")
            raise RuntimeError("Email verification required")

        # Skip if already redirected past login page
        current_url = driver.current_url
        if any(x in current_url for x in ["two_factor", "onetap", "challenge"]):
            print(f"✅ Credentials accepted — redirected to {current_url}")
        else:
            if not handle_credentials_check(
                driver=driver,
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                proxy_user=proxy_user,
                proxy_pass=proxy_pass,
            ):
                print("🛑 Credential check failed — stopping")
                if(is_last_attempt):
                    webhook.update_account_status("wrong_login_data", {
                        "account_id": webhook.account_id,
                        "profile_id": webhook.profile_id,
                        "error_type": "CREDENTIALS",
                    })
                    raise RuntimeError("Invalid Credentials Error")
                else:
                    webhook.update_account_status("update_session_and_restart_task", {
                        "account_id": webhook.account_id,
                        "profile_id": webhook.profile_id,
                        "error_type": "CREDENTIALS",
                    })  
                    return False
            
        # ── 2FA ────────────────────────────────────────────────────────────────
        if not handle_two_factor_authentication(driver, secret_key=secret_key, webhook=webhook):
            return False

        time.sleep(40)
        return True

    except (UIChangeError, RuntimeError):
            raise

    except Exception as e:
        print(f"❌ Unexpected error during login attempt: {e}")
        return False


def handle_credentials_check(
    driver,
    proxy_host: str,
    proxy_port: int,
    proxy_user: str,
    proxy_pass: str
) -> bool:
    """
    Validates that no credential error is shown after login attempt.
    
    Retry logic:
      - Up to MAX_CREDENTIAL_RETRIES attempts
      - On each failure, cross-checks connectivity:
            connectivity fail → webhook "update_session_and_restart_task" → return False
            connectivity ok   → retry login
      - After all retries exhausted → webhook "wrong_login_data" → return False
      - No error found / error was transient → return True

    Returns:
        True  → credentials accepted, login can continue
        False → unrecoverable failure, stop task
    """

    keywords = ["incorrect", "sorry", "double-check", "credentials"]

    xpath_cond = " or ".join(
            f"contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{kw}')"
            for kw in keywords
        )
    error_xpath = f"//span[{xpath_cond}]"

    print(f"\n🔐 Credential check")

    # ── Step 1: Check if any error span is visible ────────────────────────────
    try:
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.XPATH, error_xpath))
        )
    except TimeoutException:
        # No error span found at all — credentials accepted
        print("✅ No credential error detected — login proceeding")
        return True

    # ── Step 2: Error found — wait to confirm it's not transient ─────────────
    print("⚠️ Potential credential error detected, waiting to confirm it's persistent...")
    time.sleep(4)

    error_elems = driver.find_elements(By.XPATH, error_xpath)
    if not error_elems:
        print("ℹ️ Error text disappeared — was transient, login likely succeeded")
        return True

    # ── Step 3: Error is persistent — cross-check connectivity ───────────────
    error_text = error_elems[0].text.strip().lower()
    print(f"⚠️ Persistent error confirmed: '{error_text}'")
    print("🔎 Cross-checking connectivity before blaming credentials...")

    connectivity = check_connectivity(
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        proxy_user=proxy_user,
        proxy_pass=proxy_pass
    )

    # ── Step 4a: Connectivity failed — network is the culprit ─────────────────
    if not connectivity.success:
        print(f"🌐 Connectivity failed at [{connectivity.failed_at}]: {connectivity.failure_reason}")
        return False

    # ── Step 5: All retries exhausted + connectivity healthy = real bad creds ──
    print(f"❌ Credential error persisted across with healthy network")
    return False


def handle_email_verification_checkpoint(driver, webhook:WebhookUtils) -> bool:
    """
    Detects if Instagram is asking for email verification (Check your email screen).
    If detected, reports to webhook and returns False to stop login.

    Returns:
        False if email checkpoint detected (login should stop)
        True if not detected (login can continue)
    """
    try:
        # ── Detection Method 1: URL contains auth_platform/codeentry ──────────
        current_url = driver.current_url
        if "auth_platform/codeentry" in current_url:
            print("🔒 Email checkpoint detected via URL")
            webhook.update_account_status("login_manual_interuption_required", {
            "account_id": webhook.account_id,
            "metadata": "Login Stopped, Email Checkpoint Occured at: " + driver.current_url,
            })
            return False

        # ── Detection Method 2: h2 with "Check your email" text ───────────────
        try:
            h2_elems = driver.find_elements(By.CSS_SELECTOR, "h2[dir='auto']")
            for h2 in h2_elems:
                if "check your email" in h2.text.strip().lower():
                    print("🔒 Email checkpoint detected via h2 text")
                    webhook.update_account_status("login_manual_interuption_required", {
                    "account_id": webhook.account_id,
                    "metadata": "Login Stopped, Email Checkpoint Occured at: " + driver.current_url,
                })
                    return False
        except Exception as e:
            print(f"⚠️ Error scanning h2 elements: {e}")

        # ── Not detected ──────────────────────────────────────────────────────
        return True

    except Exception as e:
        print(f"⚠️ Unexpected error in email checkpoint detection: {e}")
        # Safe default — don't block login on detection failure
        return True

