"""
sendMessages.py — Production-grade Instagram DM Automation
===========================================================
Flow:
    search_and_message_users()
        ├── search_user_via_profile()   →  MESSAGE  (new DM via profile page)
        ├── search_user()               →  FOLLOWUP / REPLY_CHECK  (via inbox search)
        └── per-type handler
                MESSAGE      → check_if_existing_messages_are_present()
                                send_message_to_user()
                                check_for_reply()
                FOLLOWUP     → check_for_reply()
                                send_message_to_user()
                REPLY_CHECK  → check_for_reply()

Error hierarchy (all from exceptions.py):
    UIChangeError           — selector/XPath no longer valid
    ScriptError             — JS execute_script failure
    GologinError            — browser/session dead
    InstagramServerError    — on-page 'Something isn't working.' banner
    PageHealthError         — page unresponsive / blank
    RuntimeError (built-in) — server says STOP NOW; propagated immediately~
"""

import logging
import random
import re
import time
import unicodedata
from typing import Optional

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scripts.browseExplore import browse_explore_page
from utils.basicHelpers import find_ascii_substring
from utils.scrapping.BasicUtils import BasicUtils
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.HumanTypingBehavior import HumanTypingBehavior
from utils.scrapping.ScreenObserver import ScreenObserver
from utils.WebhookUtils import WebhookUtils
from utils.exceptions import (
    InstagramServerError,
    ScriptError,
    UIChangeError,
    UserSearchError,
    MessageRejectedError
)
import sys

MESSAGE_MAX_RETRIES: int = 2
USER_MAX_RETRIES: int = 2
INSTAGRAM_PAGE_ERROR_LIMIT: int = 4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,  # 👈 THIS is key
)

log = logging.getLogger(__name__)

def _log(level: int, username: str | None, action: str, msg: str, **extra) -> None:
    """Emit a single structured log line.

    Every line always carries `username` and `action` so log tails are
    self-contained without having to scroll up for context.
    """
    record_extra = {"ig_username": username or "-"}
    record_extra.update(extra)

    # If there are extra params, append them to the message so they appear in stdout
    if extra:
        extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
        msg = f"{msg} | {extra_str}"

    log.log(level, "[%s | %s] %s", username or "-", action, msg, extra=record_extra)


# ── Main orchestrator ─────────────────────────────────────────────────────────
def search_and_message_users(
    driver,
    messages_to_send: list[dict],
    observer: ScreenObserver,
    webhook: WebhookUtils,
    send_to_new_users_only: bool,
    delay_between_messages: tuple[int, int] = (30, 50),
) -> tuple[int, list[str]]:
    """Orchestrate the full search-and-message loop.

    Args:
        driver:                   Selenium WebDriver
        messages_to_send:         list of dicts with keys:
                                    username, messages, type,
                                    prevText (FOLLOWUP/REPLY_CHECK),
                                    serial   (FOLLOWUP)
        observer:                 ScreenObserver
        webhook:                  WebhookUtils
        send_to_new_users_only:   skip users with existing conversation
        delay_between_messages:   (min_s, max_s) inter-message pause

    Returns:
        (successful_fresh_dms, successful_messages)

    Raises:
        RuntimeError:             propagated immediately — caller must stop
        InstagramServerError:     raised when error banner limit is hit
        UIChangeError:            raised when UI changes
        ScriptError:              raised when script fails
    """

    action = "search_and_message_users"

    human_mouse = HumanMouseBehavior(driver)
    human_typing = HumanTypingBehavior(driver)
    basicUtils = BasicUtils(driver)

    successful_messages: list[str] = []
    successful_fresh_dms: int = 0

    # ── Startup: navigate to inbox ────────────────────────────────────────────
    observer.health_monitor.revive_driver("click_body")
    time.sleep(2)

    _navigate_to_inbox(driver, basicUtils, observer, human_mouse, context_label="startup")
    time.sleep(2)

    _log(logging.INFO, None, action,
         f"Starting loop — {len(messages_to_send)} users to process")

    # ── Deduplicate by username ────────────────────────────────────────────────
    seen: dict[str, dict] = {}
    for msg in messages_to_send:
        seen[msg["username"]] = msg
    messages_to_send = list(seen.values())

    if len(messages_to_send) == 0:
        raise RuntimeError("Not enough messages to process, stop the task")

    # ── Pick warmup index ─────────────────────────────────────────────────────
    warmup_index = random.randint(
        -(len(messages_to_send) * 2) + 1, len(messages_to_send) - 2
    )

    instagram_page_error_count: int = 0
    already_messaged_this_session: set[str] = set()

    # ── Per-user loop ─────────────────────────────────────────────────────────
    for i, message in enumerate(messages_to_send):
        username = message["username"]
        messages = message.get("messages", None)
        message_type = message["type"]

        _log(logging.INFO, username, action,
             f"Processing {i + 1}/{len(messages_to_send)} : @{username} — type={message_type}")

        # ── Skip duplicates within session ────────────────────────────────────
        if username in already_messaged_this_session:
            _log(logging.WARNING, username, action, "Already messaged this session — skipping")
            continue

        # ── Warmup at chosen iteration ────────────────────────────────────────
        if i == warmup_index:
            try:
                _log(logging.INFO, username, action, "Running random warmup")
                basicUtils.click_anchor_by_href("/")
                observer.health_monitor.revive_driver("click_body")
                time.sleep(2)
                random_warmup(driver=driver, observer=observer)
                time.sleep(4)
            except Exception as exc:
                _log(logging.INFO, None, action,
                     "Warmup Failed skipping to inbox navigation", error=str(exc))
                pass

            try:
                _navigate_to_inbox(driver, basicUtils, observer, human_mouse, context_label="post-warmup")
            except Exception:
                _log(logging.ERROR, None, action,
                     "Could not return to inbox after warmup — raising")
                raise

            time.sleep(3)

        # ── Per-user try block ────────────────────────────────────────────────
        try:
            # ── Choose search strategy ────────────────────────────────────────
            search_fn = (
                search_user_via_profile if message_type == "MESSAGE" else search_user
            )

            # FOLLOWUP / REPLY_CHECK: ensure inbox is open and close stray sidebars
            if message_type in ("FOLLOWUP", "REPLY_CHECK"):
                try:
                    _navigate_to_inbox(driver, basicUtils, observer, human_mouse, context_label="start-followup-or-reply-check")
                except Exception as exc:
                    _log(logging.ERROR, None, action,
                        "Could not return to inbox after starting followup or reply check", error=str(exc))
                    raise
                time.sleep(2)

            # ── Run search ────────────────────────────────────────────────────
            search_fn(
                driver, username, human_mouse, human_typing, observer
            )

            # search_fn raises SearchError on failure; reaching here means found
            _log(logging.INFO, username, action, "User found ✓")
            time.sleep(2)

            # ── Check Instagram error banner ──────────────────────────────────
            try:
                error_banner = driver.find_element(
                    By.XPATH,
                    "//span[@dir='auto']//span[contains(text(), concat('Something isn', \"'\", 't working'))]",
                )
                if error_banner and error_banner.is_displayed():
                    instagram_page_error_count += 1
                    _log(logging.ERROR, username, action,
                         f"Instagram 'Something isn't working' banner — count {instagram_page_error_count}",
                         banner_text=error_banner.text)

                    if instagram_page_error_count >= INSTAGRAM_PAGE_ERROR_LIMIT:
                        webhook.update_campaign_status(
                            "instagram_page_error",
                            {
                                "campaign_id": webhook.attributes.get("campaign_id"),
                                "page": "Messaging Page",
                            },
                        )
                        raise InstagramServerError(
                            f"Instagram page error limit reached ({INSTAGRAM_PAGE_ERROR_LIMIT})",
                            context={
                                "error_count": instagram_page_error_count,
                                "page": "Messaging Page",
                            },
                        )
                    continue
            except NoSuchElementException:
                pass

            # ── Handle by type ────────────────────────────────────────────────

            # ·· MESSAGE ·····················································
            if message_type == "MESSAGE":
                try:
                    if send_to_new_users_only and check_if_existing_messages_are_present(
                        driver, username, observer
                    ):
                        _log(logging.INFO, username, action,
                             "Existing conversation found — marking as failed (send_to_new_users_only)")
                        webhook.update_campaign_status(
                            "sent_dm",
                            {
                                "campaign_id": webhook.attributes.get("campaign_id"),
                                "username": username,
                                "data": {"already": True},
                                "type": "MESSAGE",
                                "failed": True,
                            },
                        )

                    elif send_message_to_user(
                        driver, username, messages, human_mouse, human_typing, observer
                    ):
                        successful_messages.append(username)
                        successful_fresh_dms += 1
                        webhook.update_campaign_status(
                            "sent_dm",
                            {
                                "campaign_id": webhook.attributes.get("campaign_id"),
                                "username": username,
                                "data": {},
                                "type": "MESSAGE",
                            },
                        )
                        _log(logging.INFO, username, action, "Message sent ✓")

                        # Quick reply check (10 s)
                        time.sleep(10)
                        replied = check_for_reply(
                            driver, username, observer,
                            find_ascii_substring(messages[-1], {}),
                        )
                        if replied:
                            webhook.update_campaign_status(
                                "sent_dm",
                                {
                                    "campaign_id": webhook.attributes.get("campaign_id"),
                                    "username": username,
                                    "data": {"replied": True},
                                    "type": "REPLY_CHECK",
                                },
                            )
                            _log(logging.INFO, username, action, "Immediate reply detected ✓")

                    else:
                        raise Exception(
                            f"send_message_to_user returned False for @{username}"
                        )

                except (UIChangeError, ScriptError, RuntimeError, InstagramServerError):
                    raise

                except Exception as exc:
                    _log(logging.ERROR, username, action, "MESSAGE handler error", error=str(exc))
                    webhook.update_campaign_status(
                        "sent_dm",
                        {
                            "campaign_id": webhook.attributes.get("campaign_id"),
                            "username": username,
                            "data": {},
                            "type": "MESSAGE",
                            "failed": True,
                        },
                    )

            # ·· FOLLOWUP ···················································
            elif message_type == "FOLLOWUP":
                try:
                    prevmsg = message.get("prevText")
                    replied = check_for_reply(driver, username, observer, prevmsg)
                    time.sleep(3)

                    if replied:
                        webhook.update_campaign_status(
                            "sent_dm",
                            {
                                "campaign_id": webhook.attributes.get("campaign_id"),
                                "username": username,
                                "data": {"replied": True},
                                "type": "REPLY_CHECK",
                            },
                        )
                        _log(logging.INFO, username, action,
                             "Already replied — followup skipped")

                    else:
                        if send_message_to_user(
                            driver, username, messages, human_mouse, human_typing, observer
                        ):
                            successful_messages.append(username)
                            webhook.update_campaign_status(
                                "sent_dm",
                                {
                                    "campaign_id": webhook.attributes.get("campaign_id"),
                                    "username": username,
                                    "data": {"serial": message["serial"]},
                                    "type": "FOLLOWUP",
                                },
                            )
                            _log(logging.INFO, username, action, "Followup sent ✓")
                        else:
                            raise Exception(
                                f"Followup send_message_to_user returned False for @{username}"
                            )

                except (UIChangeError, ScriptError, RuntimeError, InstagramServerError):
                    raise

                except Exception as exc:
                    _log(logging.ERROR, username, action, "FOLLOWUP handler error", error=str(exc))
                    webhook.update_campaign_status(
                        "sent_dm",
                        {
                            "campaign_id": webhook.attributes.get("campaign_id"),
                            "username": username,
                            "data": {"serial": message.get("serial")},
                            "type": "FOLLOWUP",
                            "failed": True,
                        },
                    )

            # ·· REPLY_CHECK ················································
            elif message_type == "REPLY_CHECK":
                try:
                    prevmsg = message.get("prevText")
                    replied = check_for_reply(driver, username, observer, prevmsg)
                    time.sleep(3)

                    webhook.update_campaign_status(
                        "sent_dm",
                        {
                            "campaign_id": webhook.attributes.get("campaign_id"),
                            "username": username,
                            "data": {"replied": replied},
                            "type": "REPLY_CHECK",
                        },
                    )
                    _log(logging.INFO, username, action,
                         f"Reply check complete — replied={replied}")

                except (UIChangeError, ScriptError, RuntimeError, InstagramServerError):
                    raise

                except Exception as exc:
                    _log(logging.ERROR, username, action, "REPLY_CHECK handler error", error=str(exc))

        # ── Per-user exception handling ───────────────────────────────────────
        except (UIChangeError, ScriptError, RuntimeError, InstagramServerError):
            raise

        except UserSearchError as exc:
            _log(logging.ERROR, username, action, "user not found", error=str(exc))
            webhook.update_campaign_status(
                "sent_dm",
                {
                    "campaign_id": webhook.attributes.get("campaign_id"),
                    "username": username,
                    "data": {"notFound":True},
                    "type": message_type,
                    "failed": True,
                },
            )
            continue

        except Exception as exc:
            _log(logging.ERROR, username, action, "Unhandled per-user exception", error=str(exc))

        # ── Mark as processed, wait before next user ──────────────────────────
        already_messaged_this_session.add(username)

        if i < len(messages_to_send) - 1:
            delay = random.randint(delay_between_messages[0], delay_between_messages[1])
            _log(logging.INFO, username, action,
                 f"Waiting {delay}s before next user")
            observer.health_monitor.revive_driver("screenshot")
            time.sleep(delay)

    # ── Summary ───────────────────────────────────────────────────────────────
    _log(logging.INFO, None, action,
         f"Loop complete — sent to {len(successful_messages)} users, "
         f"{successful_fresh_dms} fresh DMs",
         users=successful_messages)

    return successful_fresh_dms, successful_messages


# ── User search ───────────────────────────────────────────────────────────────
def search_user(
    driver,
    username: str,
    human_mouse: HumanMouseBehavior,
    human_typing: HumanTypingBehavior,
    observer: ScreenObserver,
    retry_delay: float = 2.0,
) -> bool:
    """Search for `username` via the inbox search bar (FOLLOWUP / REPLY_CHECK path).

    Returns:
        True  — user found and chat thread opened
        False — exhausted retries (caller should mark as failed)

    Raises:
        UserSearchError:  if USER_MAX_RETRIES exhausted with structured context
        UIChangeError: if known selectors are missing entirely
        ScriptError:   from is_page_healthy / scroll helpers
        RuntimeError:  propagated immediately (server stop signal)
    """
    action = "search_user"
    attempt = 0

    while attempt < USER_MAX_RETRIES:
        _log(logging.INFO, username, action, f"Attempt {attempt + 1}/{USER_MAX_RETRIES}")
        try:
            observer.health_monitor.revive_driver("click_body")
            observer.human_mouse.random_mouse_jitter(3,"medium")

            # ── Back button (dismiss previous result if any) ──────────────────
            back_button = (By.CSS_SELECTOR, "svg[aria-label='Back']")
            try:
                human_mouse.human_like_move_to_element(back_button, click=True)
                time.sleep(1.5)
            except Exception:
                pass

            # ── Search input ──────────────────────────────────────────────────
            search_input = (By.CSS_SELECTOR, "input[placeholder*='Search']")
            try:
                human_mouse.human_like_move_to_element(search_input, click=True)
                WebDriverWait(driver, 5).until(EC.element_to_be_clickable(search_input))
            except (TimeoutException, Exception):
                _log(logging.WARNING, username, action,
                     "Search bar not responding — reviving with scroll")
                observer.health_monitor.revive_driver("scroll")
                time.sleep(1.5)
                try:
                    human_mouse.human_like_move_to_element(search_input, click=True)
                    WebDriverWait(driver, 5).until(EC.element_to_be_clickable(search_input))
                except TimeoutException as exc:
                    raise UIChangeError(
                        "Inbox search input not clickable after scroll-revive",
                        context={"username": username, "attempt": attempt + 1},
                    ) from exc

            time.sleep(1.5)
            human_typing.human_like_type(search_input, text=username, clear_field=True)

            has_special = username.startswith("_") or "." in username
            time.sleep(4.0 if has_special else 2.5)

            # ── Wait for results ──────────────────────────────────────────────
            xpaths = [
                f"//h2[normalize-space(text())='More accounts']/following::span[text()='{username}']",
                f"//span[contains(text(),'{username}')]",
            ]

            user_result = None
            for xpath in xpaths:
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    user_result = (By.XPATH, xpath)
                    break
                except TimeoutException:
                    continue

            if user_result is None:
                _log(logging.WARNING, username, action,
                     "No results on first pass — taking screenshot and retrying")
                observer.health_monitor.revive_driver("screenshot")
                time.sleep(1.5)
                for xpath in xpaths:
                    try:
                        WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, xpath))
                        )
                        user_result = (By.XPATH, xpath)
                        break
                    except TimeoutException:
                        continue

            if user_result is None:
                _log(logging.WARNING, username, action,
                     f"No search result found (attempt {attempt + 1})")
                attempt += 1
                time.sleep(retry_delay)
                continue

            human_mouse.human_like_move_to_element(user_result, click=True)
            time.sleep(2)

            # ── Verify profile/DM thread opened ──────────────────────────────
            verify_conditions = EC.any_of(
                EC.presence_of_element_located(
                    (By.XPATH, f"//span[contains(text(),'{username} · Instagram')]")
                ),
                EC.presence_of_element_located(
                    (By.XPATH, f"//a[@href='/{username}/' and @role='link']")
                ),
            )

            try:
                WebDriverWait(driver, 10).until(verify_conditions)
                _log(logging.INFO, username, action, "User found — profile/thread confirmed")
                return True

            except TimeoutException:
                _log(logging.WARNING, username, action,
                     "Profile page did not load — single refresh justified")
                observer.health_monitor.revive_driver("refresh")
                time.sleep(2)
                try:
                    WebDriverWait(driver, 10).until(verify_conditions)
                    _log(logging.INFO, username, action, "Profile confirmed after refresh")
                    return True
                except TimeoutException:
                    _log(logging.WARNING, username, action,
                         f"Profile still not loaded (attempt {attempt + 1})")

        except (UIChangeError, ScriptError, RuntimeError):
            raise

        except Exception as exc:
            _log(logging.ERROR, username, action,
                 f"Unexpected error on attempt {attempt + 1}", error=str(exc))

        attempt += 1
        time.sleep(retry_delay)

    raise UserSearchError(
        f"Failed to find @{username} after {USER_MAX_RETRIES} attempts (inbox search)",
        context={"username": username, "attempts": USER_MAX_RETRIES},
    )


def search_user_via_profile(
    driver,
    username: str,
    human_mouse: HumanMouseBehavior,
    human_typing: HumanTypingBehavior,
    observer: ScreenObserver,
    retry_delay: float = 2.0,
) -> bool:
    """Search for `username` via the global search panel and navigate to DM thread.
    Used for the MESSAGE (new DM) flow.

    Returns:
        True  — successfully landed on /direct/t/ thread
        False — exhausted retries

    Raises:
        UserSearchError:    retries exhausted
        UIChangeError:      required DOM element missing (selector change)
        ScriptError:        JS execution failure
        RuntimeError:       propagated immediately
    """

    action = "search_user_via_profile"
    attempt = 0

    while attempt < USER_MAX_RETRIES:
        _log(logging.INFO, username, action, f"Attempt {attempt + 1}/{USER_MAX_RETRIES}")
        try:
            observer.health_monitor.revive_driver("click_body")
            observer.human_mouse.random_mouse_jitter(3,"medium")
            time.sleep(1)

            # ── STEP 1: Ensure global search panel is open ────────────────────
            search_panel_input = (
                By.CSS_SELECTOR,
                "input[aria-label='Search input'][placeholder='Search']",
            )
            panel_already_open = bool(
                driver.find_elements(
                    By.CSS_SELECTOR,
                    "input[aria-label='Search input'][placeholder='Search']",
                )
            )

            if not panel_already_open:
                search_svgs = driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Search']")
                if not search_svgs:
                    raise UIChangeError(
                        "No Search SVG found on page — sidebar selector may have changed",
                        context={"username": username, "attempt": attempt + 1},
                    )
                human_mouse.human_like_move_to_element(search_svgs[0], click=True)
                time.sleep(1.5)
                try:
                    WebDriverWait(driver, 8).until(EC.element_to_be_clickable(search_panel_input))
                except TimeoutException:
                    _log(logging.WARNING, username, action,
                         "Search panel did not open — reviving and retrying")
                    observer.health_monitor.revive_driver("click_body")
                    observer.human_mouse.random_mouse_jitter(2,"high")
                    time.sleep(1.5)
                    try:
                        WebDriverWait(driver, 8).until(
                            EC.element_to_be_clickable(search_panel_input)
                        )
                    except TimeoutException as exc:
                        raise UIChangeError(
                            "Global search panel failed to open after revive",
                            context={"username": username, "attempt": attempt + 1},
                        ) from exc

            # ── STEP 2: Type username ──────────────────────────────────────────
            human_mouse.human_like_move_to_element(search_panel_input, click=True)
            time.sleep(1)
            human_typing.human_like_type(search_panel_input, text=username, clear_field=True)

            has_special = username.startswith("_") or "." in username
            time.sleep(4.0 if has_special else 2.5)

            # ── STEP 3: Verify search results loaded ──────────────────────────
            results_xpath = (
                "//div[contains(@class,'html-div')]/a[@role='link' and .//a[@role='link']]"
            )
            results_loaded = False
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, results_xpath))
                )
                results_loaded = True
            except TimeoutException:
                pass

            if not results_loaded:
                _log(logging.WARNING, username, action,
                     f"Search results did not load (attempt {attempt + 1}) — recovery")
                if attempt == 0:
                    _log(logging.INFO, username, action,
                         "Recovery 1: closing and reopening search panel")
                    try:
                        close_btn = driver.find_element(
                            By.XPATH, "//div[@aria-label='Close' and @role='button']"
                        )
                        if close_btn.is_displayed():
                            human_mouse.human_like_move_to_element(close_btn, click=True)
                            time.sleep(1.5)
                    except NoSuchElementException:
                        pass

                elif attempt == 1:
                    _log(logging.INFO, username, action, "Recovery 2: refreshing page")
                    observer.health_monitor.revive_driver("refresh")
                    time.sleep(4)

                else:
                    _log(logging.ERROR, username, action,
                         f"Search results never loaded after {attempt + 1} attempts — giving up")

                attempt += 1
                time.sleep(retry_delay)
                continue

            # ── STEP 4: Find exact profile link ───────────────────────────────
            profile_link_xpath = (
                f"//a[@href='/{username}/' and @role='link'] | "
                f"//a[@href='/{username}' and @role='link']"
            )

            user_result = None
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.XPATH, profile_link_xpath))
                )
                user_result = driver.find_element(By.XPATH, profile_link_xpath)
            except TimeoutException:
                _log(logging.WARNING, username, action,
                     "Profile link not immediately visible — taking screenshot")
                observer.health_monitor.revive_driver("screenshot")
                observer.human_mouse.random_mouse_jitter(2,"medium")
                matches = driver.find_elements(By.XPATH, profile_link_xpath)
                user_result = matches[0] if matches else None

            if user_result is None:
                _log(logging.WARNING, username, action,
                     f"No profile link found (attempt {attempt + 1})")
                _log(logging.INFO, username, action,
                         "Recovery: closing and reopening search panel")
                try:
                    close_btn = driver.find_element(
                        By.XPATH, "//div[@aria-label='Close' and @role='button']"
                    )
                    if close_btn.is_displayed():
                        human_mouse.human_like_move_to_element(close_btn, click=True)
                        time.sleep(1.5)
                except NoSuchElementException:
                    pass
                attempt += 1
                time.sleep(retry_delay)
                continue

            human_mouse.human_like_move_to_element(user_result, click=True)
            time.sleep(2)

            # ── STEP 5: Wait for profile page ─────────────────────────────────
            try:
                WebDriverWait(driver, 10).until(EC.url_contains(f"/{username}/"))
                time.sleep(2)
            except TimeoutException:
                _log(logging.WARNING, username, action,
                     "Profile page did not load — click_body revive")
                observer.health_monitor.revive_driver("click_body")
                time.sleep(3)
                try:
                    WebDriverWait(driver, 10).until(EC.url_contains(f"/{username}/"))
                except TimeoutException:
                    _log(logging.WARNING, username, action,
                         f"Profile still not loaded (attempt {attempt + 1})")
                    attempt += 1
                    time.sleep(retry_delay)
                    continue

            # ── STEP 6: Detect public vs private; find Message button ─────────
            message_btn_xpath = "//div[@role='button' and normalize-space(text())='Message']"
            options_svg_css = "svg[aria-label='Options']"

            message_btn = None
            is_private = False

            observer.health_monitor.revive_driver("screenshot")
            observer.human_mouse.random_mouse_jitter(4,"medium")

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, message_btn_xpath))
                )
                message_btn = driver.find_element(By.XPATH, message_btn_xpath)
            except TimeoutException:
                _log(logging.INFO, username, action,
                     "No Direct 'Message' button — checking if private account")
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, options_svg_css))
                    )
                    is_private = True
                    _log(logging.INFO, username, action, "Private account confirmed")
                except TimeoutException:
                    _log(logging.WARNING, username, action,
                         "Neither Message button nor Options SVG found — page not loaded?")
                    if attempt < USER_MAX_RETRIES - 1:
                        observer.health_monitor.revive_driver("refresh")
                        time.sleep(6)
                    attempt += 1
                    time.sleep(retry_delay)
                    continue

            # ── STEP 7: Click Message / Options → message ─────────────────────
            if not is_private:
                human_mouse.human_like_move_to_element(message_btn, click=True)
                try:
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
                    )
                    dialog_msg_btn = driver.find_element(
                        By.XPATH,
                        "//div[@role='dialog']//button[contains(text(),'message request')]",
                    )
                    human_mouse.human_like_move_to_element(dialog_msg_btn, click=True)
                except TimeoutException:
                    _log(logging.INFO, username, action,
                         "Dialog did not appear for public account — sidebar may have opened instead")
            else:
                options_svg = driver.find_element(By.CSS_SELECTOR, options_svg_css)
                human_mouse.human_like_move_to_element(options_svg, click=True)
                time.sleep(1.5)
                try:
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
                    )
                    dialog_msg_btn = driver.find_element(
                        By.XPATH,
                        "//div[@role='dialog']//button[contains(text(),'message')]",
                    )
                    human_mouse.human_like_move_to_element(dialog_msg_btn, click=True)
                    time.sleep(10)
                except TimeoutException:
                    _log(logging.WARNING, username, action,
                         "Dialog did not appear for private account")
                    attempt += 1
                    time.sleep(retry_delay)
                    continue

            # ── STEP 8: Verify DM thread URL ──────────────────────────────────
            try:
                WebDriverWait(driver, 8).until(EC.url_contains("/direct/t/"))
                _log(logging.INFO, username, action, "Landed on DM thread ✓")
                time.sleep(2)
                return True

            except TimeoutException:
                # Public account only: check for sidebar fallback
                if not is_private:
                    _log(logging.INFO, username, action,
                         "Did not land on /direct/t/ — checking sidebar fallback")
                    try:
                        WebDriverWait(driver, 6).until(
                            EC.presence_of_element_located(
                                (By.XPATH, "//div[contains(@aria-label,'Conversation with')]")
                            )
                        )

                        # Confirm it's the right conversation
                        try:
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located(
                                    (
                                        By.XPATH,
                                        f"//div[contains(@aria-label,'Conversation with')]"
                                        f"//span[contains(text(),'{username}')]",
                                    )
                                )
                            )
                            _log(logging.INFO, username, action,
                                 "Correct conversation confirmed in sidebar")
                        except TimeoutException:
                            _log(logging.WARNING, username, action,
                                 "Wrong conversation loaded — closing sidebar and retrying")
                            try:
                                close_btn = driver.find_element(
                                    By.XPATH, "//div[@aria-label='Close' and @role='button']"
                                )
                                if close_btn.is_displayed():
                                    human_mouse.human_like_move_to_element(close_btn, click=True)
                                    time.sleep(1.5)
                            except NoSuchElementException:
                                pass
                            attempt += 1
                            time.sleep(retry_delay)
                            continue

                        # Expand sidebar → full DM thread
                        expand_svg = driver.find_element(
                            By.CSS_SELECTOR, "svg[aria-label='Expand']"
                        )
                        human_mouse.human_like_move_to_element(expand_svg, click=True)
                        observer.human_mouse.random_mouse_jitter(5,"medium")
                        time.sleep(3)

                        WebDriverWait(driver, 6).until(EC.url_contains("/direct/t/"))
                        _log(logging.INFO, username, action,
                             "Landed on DM thread via sidebar Expand ✓")
                        time.sleep(2)
                        return True

                    except Exception as sidebar_exc:
                        _log(logging.WARNING, username, action,
                             "Sidebar fallback failed", error=str(sidebar_exc))
                        attempt += 1
                        time.sleep(retry_delay)
                        continue
                else:
                    _log(logging.WARNING, username, action,
                         "Private account: did not land on /direct/t/, retrying")
                    attempt += 1
                    time.sleep(retry_delay)
                    continue

        except (UIChangeError, ScriptError, RuntimeError):
            raise 

        except Exception as exc:
            _log(logging.ERROR, username, action, "Unexpected error on attempt", error=str(exc))
            attempt += 1
            time.sleep(retry_delay)

    raise UserSearchError(
        f"Failed to reach DM thread for @{username} after {USER_MAX_RETRIES} attempts",
        context={"username": username, "attempts": USER_MAX_RETRIES},
    )


# ── Send message ──────────────────────────────────────────────────────────────
def send_message_to_user(
    driver,
    username: str,
    messages: list[str],
    human_mouse: HumanMouseBehavior,
    human_typing: HumanTypingBehavior,
    observer: ScreenObserver
) -> bool:
    """Type and send each string in `messages` sequentially to the open DM thread.

    Returns:
        True  — all messages sent and verified
        False — a message failed (already logged; caller handles webhook)

    Raises:
        MessageRejectedError: Instagram showed 'Failed to send' — caller must stop
        UIChangeError:        textbox selector broken
        RuntimeError:         propagated immediately
    """
    action = "send_message_to_user"

    try:
        for message_text in messages:
            retries = 0
            sent = False

            while retries <= MESSAGE_MAX_RETRIES and not sent:
                _log(logging.INFO, username, action,
                     f"Sending message (retry {retries}/{MESSAGE_MAX_RETRIES})",
                     msg_preview=message_text[:60])
                try:
                    # ── Locate textbox ────────────────────────────────────────
                    try:
                        message_input = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, "div[role='textbox']")
                            )
                        )
                    except TimeoutException as exc:
                        raise UIChangeError(
                            "DM textbox not found within timeout — selector may have changed",
                            context={"username": username},
                        ) from exc

                    # ── Type message ──────────────────────────────────────────
                    try:
                        val1 = human_mouse.human_like_move_to_element(
                            message_input, click=True
                        )
                        val2 = human_typing.human_like_type(message_input, message_text)
                        if not (val1 and val2):
                            raise Exception("Interaction returned False")
                    except Exception as type_exc:
                        _log(logging.WARNING, username, action,
                             "Message input stale/failed", error=str(type_exc))
                        observer.health_monitor.revive_driver("screenshot")
                        time.sleep(3)

                        try:
                            message_input = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, "div[role='textbox']")
                                )
                            )
                            val1 = human_mouse.human_like_move_to_element(
                                message_input, click=True
                            )
                            val2 = human_typing.human_like_type(message_input, message_text)
                            if not (val1 and val2):
                                raise Exception("Interaction returned False after revive")
                        except TimeoutException as exc:
                            raise UIChangeError(
                                "DM textbox not found after screenshot revive",
                                context={"username": username},
                            ) from exc

                    # ── Send ──────────────────────────────────────────────────
                    time.sleep(1.5)
                    observer.health_monitor.revive_driver("screenshot")
                    message_input.send_keys(Keys.RETURN)

                    # ── Verify ────────────────────────────────────────────────
                    success, reason = verify_message_sent(
                        driver, username, message_text, observer
                    )

                    if success:
                        sent = True
                        _log(logging.INFO, username, action,
                             f"Message delivered ✓ (reason={reason})")

                    else:
                        retries += 1
                        if retries <= MESSAGE_MAX_RETRIES:
                            _log(logging.WARNING, username, action,
                                 f"Not confirmed ({reason}) — retry {retries}")
                            time.sleep(2)
                        else:
                            _log(logging.ERROR, username, action,
                                 f"Failed after {MESSAGE_MAX_RETRIES} retries")
                            return False

                except (MessageRejectedError, UIChangeError, RuntimeError):
                    raise

                except Exception as inner_exc:
                    _log(logging.ERROR, username, action, "Inner error sending message", error=str(inner_exc))
                    return False

        return True

    except (MessageRejectedError, UIChangeError, RuntimeError):
        raise

    except Exception as exc:
        _log(logging.ERROR, username, action, "Fatal outer error", error=str(exc))
        return False


def is_message_sent(driver, expected_text: str) -> bool:
    """Return True if `expected_text` appears in the last three chat bubbles.

    Raises:
        UIChangeError: if the chat-bubble selector returns zero elements after
                       a successful wait (selector likely changed).
    """
    try:
        chat_elems = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, 'div[role="presentation"] > span[dir="auto"]')
            )
        )
    except TimeoutException as exc:
        raise UIChangeError(
            "Chat bubble selector timed out — Instagram may have changed the DOM",
            context={"selector": 'div[role="presentation"] > span[dir="auto"]'},
        ) from exc

    if not chat_elems:
        _log(logging.WARNING, None, "is_message_sent", "No chat elements found after wait")
        return False

    expected_msg = normalize_text(expected_text)
    for elem in reversed(chat_elems[-3:]):
        msg = normalize_text(elem.text)
        if msg == expected_msg or msg.startswith(expected_msg):
            return True

    _log(logging.DEBUG, None, "is_message_sent", "Expected text not in last 3 bubbles",
         expected=expected_msg[:20])
    return False


def verify_message_sent(driver, username: str, message_text: str, observer: ScreenObserver) -> tuple[bool, str]:
    """Verify a DM was actually delivered after pressing RETURN.

    Returns:
        (True,  "sending_indicator")  — spinner appeared and cleared cleanly
        (True,  "found_in_chat")      — text confirmed in DOM (with or without refresh)
        (False, "failed_svg")         — Instagram showed 'Failed to send'  → caller MUST stop
        (False, "not_in_chat")        — not in DOM after refresh
        (False, "error")              — unexpected exception (already logged)

    Raises:
        MessageRejectedError: on "failed_svg" so the caller does not need to
                              pattern-match on the string tuple.
        UIChangeError: if chat selectors are broken.
    """
    action = "verify_message_sent"

    try:
        # ── CHECK 1: Sending spinner ──────────────────────────────────────────
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "svg[aria-label='IGD message sending status icon']")
                )
            )
            _log(logging.DEBUG, username, action, "Sending spinner detected, polling until clear")

            deadline = time.time() + 10
            while time.time() < deadline:
                # Check for hard failure first
                if driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Failed to send']"):
                    _log(logging.ERROR, username, action,
                         "Instagram 'Failed to send' SVG detected — hard stop")
                    raise MessageRejectedError(
                        "Instagram rejected the DM (Failed-to-send SVG)",
                        context={"username": username, "message": message_text[:80]},
                    )

                if not driver.find_elements(
                    By.CSS_SELECTOR, "svg[aria-label='IGD message sending status icon']"
                ):
                    _log(logging.INFO, username, action, "Spinner cleared — message delivered")
                    return True, "sending_indicator"

                time.sleep(0.5)

            _log(logging.WARNING, username, action, "Spinner never cleared within 10 s, falling back to chat check")

        except TimeoutException:
            # Spinner never appeared — not necessarily bad
            _log(logging.DEBUG, username, action, "No spinner appeared, checking for failure SVG")
            if driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Failed to send']"):
                _log(logging.ERROR, username, action,
                     "Instagram 'Failed to send' SVG found (no spinner path)")
                raise MessageRejectedError(
                    "Instagram rejected the DM (Failed-to-send SVG, no spinner)",
                    context={"username": username, "message": message_text[:80]},
                )

        # ── CHECK 2: Scan DOM before spending a refresh ───────────────────────
        _log(logging.DEBUG, username, action, "Checking chat DOM before refresh")
        if is_message_sent(driver, message_text):
            _log(logging.INFO, username, action, "Message confirmed in chat DOM (no refresh needed)")
            return True, "found_in_chat"

        # ── CHECK 3: Refresh only now that DOM check failed ───────────────────
        _log(logging.INFO, username, action, "Message not visible yet — refreshing to confirm")
        observer.health_monitor.revive_driver("refresh")
        time.sleep(3)

        if is_message_sent(driver, message_text):
            _log(logging.INFO, username, action, "Message confirmed in chat after refresh")
            return True, "found_in_chat"

        _log(logging.WARNING, username, action, "Message NOT found in chat after refresh")
        return False, "not_in_chat"

    except (MessageRejectedError, UIChangeError):
        raise

    except Exception as exc:
        _log(logging.ERROR, username, action, "Unexpected error", error=str(exc))
        return False, "error"


# ── Scroll helpers ────────────────────────────────────────────────────────────

_DM_SCROLL_CONTAINER_XPATH = '//div[@data-pagelet="IGDMessagesList"]/div'


def scroll_until_prev_text_visible(driver, prev_text: str, max_scrolls: int = 15) -> bool:
    """Scroll the DM container upward until `prev_text` is in the DOM.

    Raises:
        UIChangeError: if the scroll container is not found (pagelet renamed).
    """
    try:
        container = driver.find_element(By.XPATH, _DM_SCROLL_CONTAINER_XPATH)
    except NoSuchElementException as exc:
        raise UIChangeError(
            "DM scroll container not found — Instagram may have renamed the pagelet",
            context={"xpath": _DM_SCROLL_CONTAINER_XPATH},
        ) from exc

    # Already in DOM?
    matches = driver.find_elements(
        By.XPATH, f'//span[@dir="auto" and contains(.,"{prev_text}")]'
    )
    if matches:
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
                matches[0],
            )
        except Exception as exc:
            raise ScriptError(
                "scrollIntoView failed",
                context={"original": str(exc)},
            ) from exc
        time.sleep(0.4)
        return True

    for attempt in range(max_scrolls):
        try:
            driver.execute_script("arguments[0].scrollTop -= 300;", container)
        except Exception as exc:
            raise ScriptError(
                "scrollTop manipulation failed",
                context={"attempt": attempt, "original": str(exc)},
            ) from exc
        time.sleep(0.8)

        matches = driver.find_elements(
            By.XPATH, f'//span[@dir="auto" and contains(.,"{prev_text}")]'
        )
        if matches:
            _log(logging.DEBUG, None, "scroll_until_prev_text_visible",
                 f"Found prev_text after {attempt + 1} scroll(s)")
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
                    matches[0],
                )
            except Exception as exc:
                raise ScriptError("scrollIntoView failed", context={"original": str(exc)}) from exc
            time.sleep(0.4)
            return True

    _log(logging.WARNING, None, "scroll_until_prev_text_visible",
         f"prev_text not found after {max_scrolls} scrolls", prev_text=prev_text[:60])
    return False


def scroll_to_bottom_message_container(driver) -> None:
    """Scroll the DM container to the most recent messages.

    Raises:
        UIChangeError: container not found.
        ScriptError:   scrollTop assignment failed.
    """
    try:
        container = driver.find_element(By.XPATH, _DM_SCROLL_CONTAINER_XPATH)
    except NoSuchElementException as exc:
        raise UIChangeError(
            "DM scroll container not found when scrolling to bottom",
            context={"xpath": _DM_SCROLL_CONTAINER_XPATH},
        ) from exc
    try:
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight;", container
        )
    except Exception as exc:
        raise ScriptError(
            "scrollTop = scrollHeight failed",
            context={"original": str(exc)},
        ) from exc
    time.sleep(0.4)


# ── Reply/ Existing messages checks ──────────────────────────────────────────

def check_if_existing_messages_are_present(
    driver, username: str, observer: ScreenObserver
) -> bool:
    """Return True if there are any prior messages in the open DM thread."""
    action = "check_existing_messages"
    try:
        observer.health_monitor.revive_driver("click_body")
        observer.human_mouse.random_mouse_jitter(3,"medium")

        chat_containers = driver.find_elements(
            By.CSS_SELECTOR, 'div[data-virtualized="false"]'
        )
        message_spans = driver.find_elements(
            By.CSS_SELECTOR, 'div[role="presentation"] > span[dir="auto"]'
        )

        has_messages = bool(chat_containers) or bool(message_spans)
        _log(logging.DEBUG, username, action,
             f"Existing messages: {has_messages}",
             containers=len(chat_containers), spans=len(message_spans))
        return has_messages

    except Exception as exc:
        _log(logging.ERROR, username, action, "Error", error=str(exc))
        return False


def check_for_reply(
    driver, username: str, observer: ScreenObserver, prev_text: Optional[str] = None
) -> bool:
    """Return True if the recipient has replied in the open DM thread."""
    action = "check_for_reply"
    try:
        observer.health_monitor.revive_driver("click_body")
        observer.human_mouse.random_mouse_jitter(2,"medium")
        time.sleep(1)

        # ── Old method: look for sender anchor in last virtual container ──────
        chat_containers = driver.find_elements(
            By.CSS_SELECTOR, 'div[data-virtualized="false"]'
        )
        if chat_containers:
            last_elem = chat_containers[-1]
            anchors = last_elem.find_elements(
                By.CSS_SELECTOR, f'a[href*="/{username}"]'
            )
            if anchors:
                _log(logging.INFO, username, action, "Reply detected via old method (anchor)")
                return True

        # ── New method: XPath relative to prev_text bubble ───────────────────
        if prev_text is not None:
            found = scroll_until_prev_text_visible(driver, prev_text)
            if not found:
                scroll_to_bottom_message_container(driver)
                prev_text = None

        if prev_text is not None:
            reply_xpath = (
                f'//div[@role="none" and '
                f'../../preceding-sibling::*[.//a[@role="link" and contains(@href,"/{username}")]] '
                f'and preceding::div[@role="none"]'
                f'[.//span[@dir="auto" and contains(.,"{prev_text}")]]] '
                f'//span[@dir="auto"]'
            )
        else:
            reply_xpath = (
                f'//div[@role="none" and '
                f'../../preceding-sibling::*[.//a[@role="link" and contains(@href,"/{username}")]]] '
                f'//span[@dir="auto"]'
            )

        message_spans = driver.find_elements(By.XPATH, reply_xpath)
        if message_spans:
            _log(logging.INFO, username, action, "Reply detected via new XPath method")
            return True

        _log(logging.INFO, username, action, "No reply found")
        return False

    except (UIChangeError, ScriptError):
        raise

    except Exception as exc:
        _log(logging.ERROR, username, action, "Error", error=str(exc))
        return False


# ── utility functions ───────────────────────────────────────────────────────────────
def random_warmup(driver, observer: ScreenObserver) -> None:
    """Run a random warmup action (explore page browse) to simulate organic behaviour."""
    action = "random_warmup"
    try:
        time.sleep(3)
        browse_explore_page(driver, observer)
    except Exception as exc:
        _log(logging.ERROR, None, action, "Warmup error (non-fatal)", error=str(exc))


def _navigate_to_inbox(
    driver,
    basicUtils: BasicUtils,
    observer: ScreenObserver,
    human_mouse:HumanMouseBehavior,
    context_label: str = "initial",
) -> None:
    """Click the inbox anchor and wait for /direct/inbox URL.
    """
    action = "navigate_to_inbox"

    try:
        current_url = driver.current_url
         # check if there is any sidebar etc opened then close it
        try:
            close_btn = driver.find_element(
                By.XPATH,
                "//div[@aria-label='Close' and @role='button']"
            )
            if close_btn.is_displayed():
                _log(logging.WARNING, None, action,
                    f"[{context_label}] Sidebar still open, closing it...")
                human_mouse.human_like_move_to_element(close_btn, click=True)
                time.sleep(1.5)
                _log(logging.INFO, None, action,
                    f"[{context_label}] Sidebar closed.")
        except NoSuchElementException:
            pass

        if "/direct/" not in current_url:
            basicUtils.click_anchor_by_href("/direct/inbox/")
            time.sleep(5)
        else:
            _log(logging.INFO, None, action,
                "Already on inbox page")
            return

        # Only refresh if the page is actually unresponsive
        try:
            is_healthy = is_page_healthy(driver)
        except Exception:
            is_healthy = False

        if not is_healthy:
            _log(logging.WARNING, None, action,
                f"[{context_label}] Page unhealthy before inbox — reviving")
            observer.health_monitor.revive_driver("refresh")
            time.sleep(4)

        try:
            WebDriverWait(driver, 10).until(EC.url_contains("/direct/inbox"))
            time.sleep(5)
            return
        except TimeoutException:
            pass

        # Second attempt
        _log(logging.WARNING, None, action,
            f"[{context_label}] First inbox wait timed out — click_body revive")
        try:
            is_healthy = is_page_healthy(driver)
        except Exception:
            is_healthy = False

        if not is_healthy:
            observer.health_monitor.revive_driver("refresh")
            time.sleep(2)

        observer.health_monitor.revive_driver("click_body")

        try:
            WebDriverWait(driver, 12).until(EC.url_contains("/direct/inbox"))
            return
        except TimeoutException as exc:
            raise Exception()

    except Exception as exc:
        raise Exception(f"Could not reach /direct/inbox/ [{context_label}], error: {str(exc)}")


def is_page_healthy(driver) -> bool:
    """Return True if the page is responsive — JS runs, readyState is
    'complete', and the URL is not blank.
    """
    try:
        ready = driver.execute_script("return document.readyState")
        if ready != "complete":
            return False

        current_url = driver.current_url
        if not current_url or current_url in ("about:blank", "data:,"):
            return False

        driver.execute_script("return 1")
        return True

    except Exception:
        return False


def normalize_text(s: str) -> str:
    """Normalize unicode, collapse whitespace — used for chat verification."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()
