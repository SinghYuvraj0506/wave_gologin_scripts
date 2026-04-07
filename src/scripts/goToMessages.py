from utils.scrapping.BandwidthTracker import BandwidthTracker
import time
import random
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.HumanTypingBehavior import HumanTypingBehavior
from utils.scrapping.BasicUtils import BasicUtils
from selenium.webdriver.common.keys import Keys
from utils.scrapping.ScreenObserver import ScreenObserver
from utils.WebhookUtils import WebhookUtils
from utils.basicHelpers import find_ascii_substring
from scripts.browseExplore import browse_explore_page
import unicodedata
import re

MESSAGE_MAX_RETRIES = 2
USER_MAX_RETRIES = 2

def search_and_message_users(driver, messages_to_send, observer: ScreenObserver, webhook: WebhookUtils, bandwidthTracker: BandwidthTracker, send_to_new_users_only,  delay_between_messages=(30, 50)):
    """
    Search for usernames and send messages to them if available.

    Args:
        driver: Selenium WebDriver instance
        usernames_list: List of usernames to search for
        message_text: Message to send to each user
        delay_between_messages: Tuple of (min, max) seconds to wait between messages
    """
    human_mouse = HumanMouseBehavior(driver)
    human_typing = HumanTypingBehavior(driver)
    basicUtils = BasicUtils(driver)

    successful_messages = []
    successful_fresh_dms = 0
    failed_users = []

    observer.health_monitor.revive_driver("click_body")
    time.sleep(2)

    basicUtils.click_anchor_by_href("/direct/inbox/")
    time.sleep(5)

     # ✅ Only refresh if the page is actually unresponsive
    if not is_page_healthy(driver):
        observer.health_monitor.revive_driver("refresh")
        time.sleep(3)

    # Check if we're on a valid user profile
    try:
        WebDriverWait(driver, 10).until(
            EC.url_contains("/direct/inbox")
        )
        time.sleep(5)

    except TimeoutException:
        try:
            if not is_page_healthy(driver):
                observer.health_monitor.revive_driver("refresh")
                time.sleep(2)

            observer.health_monitor.revive_driver("click_body")
            WebDriverWait(driver, 12).until(
                EC.url_contains("/direct/inbox")
            )
        except Exception as e:
            raise Exception("Page not clicked")

    print(f"🔍 Starting to search and message {len(messages_to_send)} users...")
    time.sleep(4)

    # 👇 Pick a random iteration for warmup , no warmuo befire the last iterations
    warmup_index = random.randint(-(len(messages_to_send)*2) +
                                  1, len(messages_to_send) - 2)

    # check for replies on the top of the chat at once -----------


    # message sending loop ---------------------------------------
    for i, message in enumerate(messages_to_send):
        print(
            f"\n📝 Processing user {i+1}/{len(messages_to_send)}: @{message['username']}")

        # 👇 If current iteration is the chosen one, run warmup
        if i == warmup_index:
            basicUtils.click_anchor_by_href("/")
            observer.health_monitor.revive_driver("click_body")
            time.sleep(2)

            print("🔥 Running random warmup...")
            random_warmup(driver=driver, observer=observer)
            time.sleep(4)

            basicUtils.click_anchor_by_href("/direct/inbox/")
            time.sleep(4)
            
            # ✅ Only refresh if page didn't load properly
            try:
                WebDriverWait(driver, 10).until(
                    EC.url_contains("/direct/inbox")
                )
            except TimeoutException:
                # First real sign something is wrong — now refresh is justified
                if not is_page_healthy(driver):
                    observer.health_monitor.revive_driver("refresh")

                observer.health_monitor.revive_driver("screenshot")
                
                try:
                    WebDriverWait(driver, 10).until(
                        EC.url_contains("/direct/inbox")
                    )
                except Exception as e:
                    raise Exception("Page not clicked") from e

            time.sleep(3)

        username = message['username']
        messages = message['messages']
        message_type = message['type']

        try:
            # Search for the username
            if search_user(driver, username, human_mouse, human_typing,bandwidthTracker, observer):
                print(f"✅ User @{username} found!")
                time.sleep(2)

                bandwidthTracker.set_action("Sending message to user")

                if message_type == "MESSAGE":
                    if (send_to_new_users_only and check_if_existing_messages_are_present(driver, username, observer)):
                        raise Exception( f"❌ Username @{username} has previous chats with the ig user, hence marking as failed")

                    if send_message_to_user(driver, username, messages, human_mouse, human_typing, observer, webhook):
                        successful_messages.append(username)
                        successful_fresh_dms += 1
                        webhook.update_campaign_status("sent_dm", {
                            "campaign_id": webhook.attributes.get("campaign_id", None),
                            "username": username,
                            "data": {},
                            "type": "MESSAGE"
                        })
                        print(f"✅ Message sent to @{username}")

                        # wait for 10 seconds for reply check and if replied then send the webhook as replied
                        time.sleep(10)
                        replied = check_for_reply(driver, username, observer, find_ascii_substring(messages[-1],{}))

                        if replied:
                            webhook.update_campaign_status("sent_dm", {
                                "campaign_id": webhook.attributes.get("campaign_id", None),
                                "username": username,
                                "data": {
                                    "replied": True
                                },
                                "type": "MESSAGE"
                            })


                    else:
                        raise Exception(
                            f"❌ Failed to send message to @{username}")

                else:
                    prevmsg = message.get("prevText")
                    replied = check_for_reply(driver, username, observer, prevmsg)
                    time.sleep(3)

                    # user has replied do not followup -------
                    if replied:
                        webhook.update_campaign_status("sent_dm", {
                            "campaign_id": webhook.attributes.get("campaign_id", None),
                            "username": username,
                            "data": {
                                "serial": message["serial"],
                                "replied": True
                            },
                            "type": "FOLLOWUP"
                        })

                    else:
                        if send_message_to_user(driver, username, messages, human_mouse, human_typing, observer, webhook):
                            successful_messages.append(username)
                            webhook.update_campaign_status("sent_dm", {
                                "campaign_id": webhook.attributes.get("campaign_id", None),
                                "username": username,
                                "data": {
                                    "serial": message["serial"],
                                    "replied": False
                                },
                                "type": "FOLLOWUP"
                            })
                            print(f"✅ Followup sent to @{username}")

                        else:
                            raise Exception(
                                f"❌ Failed to send followup to @{username}")

            else:
                raise Exception(f"❌ User @{username} not found, skipping...")

        except RuntimeError as r:
            raise

        except Exception as e:
            failed_users.append(f"{username} (error: {str(e)})")
            print(f"❌ Error processing @{username}: {str(e)}")
            webhook.update_campaign_status("sent_dm", {
                "campaign_id": webhook.attributes.get("campaign_id", None),
                "username": username,
                "data": {},
                "type": "MESSAGE",
                "failed": True
            })

        # Random delay between messages to avoid rate limiting
        if i < len(messages_to_send) - 1:  # Don't wait after the last user
            delay = random.randint(
                delay_between_messages[0], delay_between_messages[1])
            print(f"⏱️ Waiting {delay} seconds before next user...")
            observer.health_monitor.revive_driver("screenshot")
            time.sleep(delay)

    # Print summary
    print(f"\n📊 Summary:")
    print(f"✅ Successfully messaged: {len(successful_messages)} users")
    print(f"❌ Failed/Not found: {len(failed_users)} users")

    if successful_messages:
        print(
            f"✅ Successful messages sent to: {', '.join(successful_messages)}")

    if failed_users:
        print(f"❌ Failed users: {', '.join(failed_users)}")

    return successful_fresh_dms, successful_messages, failed_users


def search_user(driver, username: str, human_mouse: HumanMouseBehavior, human_typing: HumanTypingBehavior, bandwidthTracker: BandwidthTracker, observer: ScreenObserver, retry_delay: float = 2.0):
    """
    Search for a specific username on Instagram.

    Args:
        driver: Selenium WebDriver instance
        username: Username to search for
        human_mouse: HumanMouseBehavior instance
        human_typing: HumanTypingBehavior instance

    Returns:
        bool: True if user found, False otherwise
    """
    attempt = 0
    bandwidthTracker.set_action("Searching for user")

    while attempt < USER_MAX_RETRIES:
        try:
            observer.health_monitor.revive_driver("click_body")

            # Click back if previous text exists
            back_button = (By.CSS_SELECTOR, "svg[aria-label='Back']")
            try:
                human_mouse.human_like_move_to_element(back_button, click=True)
                time.sleep(1.5)
            except Exception:
                pass

            # Click search bar — if it's not interactable, THEN scroll to recover
            search_input = (By.CSS_SELECTOR, "input[placeholder*='Search']")
            try:
                human_mouse.human_like_move_to_element(search_input, click=True)
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(search_input))
            except (TimeoutException, Exception):
                # ✅ Search bar not responding — now scroll revive is justified
                observer.health_monitor.revive_driver("scroll")
                time.sleep(1.5)
                human_mouse.human_like_move_to_element(search_input, click=True)
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(search_input))

            time.sleep(1.5)
            human_typing.human_like_type(
                search_input, text=username, clear_field=True)

            # Extra wait for special usernames (leading _ or containing .)
            has_special = username.startswith('_') or '.' in username
            time.sleep(4.0 if has_special else 2.5)

            # Wait for search results to appear and find the exact user
            xpaths = [
                f"//h2[normalize-space(text())='More accounts']/following::span[text()='{username}']",
                f"//span[contains(text(),'{username}')]"
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
                observer.health_monitor.revive_driver("screenshot")
                time.sleep(1.5)

                # Retry search results one more time after revive
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
                print(f"⚠️ Attempt {attempt+1}: No results found for @{username}")
                attempt += 1
                time.sleep(retry_delay)
                continue

            human_mouse.human_like_move_to_element(user_result, click=True)
            time.sleep(2)

            verify_conditions = EC.any_of(
                EC.presence_of_element_located(
                    (By.XPATH, f"//span[contains(text(),'{username} · Instagram')]")
                ),
                EC.presence_of_element_located(
                    (By.XPATH, f"//a[@href='/{username}/' and @role='link']")
                )
            )

            # ✅ After clicking a result, wait for navigation first —
            try:
                WebDriverWait(driver, 10).until(verify_conditions)
                return True

            except TimeoutException:
                observer.health_monitor.revive_driver("refresh")
                time.sleep(2)

                try:
                    WebDriverWait(driver, 10).until(verify_conditions)
                    return True
                except TimeoutException:
                    print(f"⚠️ Attempt {attempt+1}: Profile page did not load for @{username}")
                        
        except Exception as e:
            print(f"❌ Attempt {attempt+1}: Error searching for @{username}: {str(e)}")

        # Retry delay before next attempt
        attempt += 1
        time.sleep(retry_delay)
    
    print(f"❌ Failed to find user @{username} after {USER_MAX_RETRIES} attempts")
    return False


def normalize_text(s: str) -> str:
    """Normalize text for comparison (handles emojis, whitespace, unicode)."""
    if not s:
        return ""
    # Normalize Unicode (NFKC makes emojis and symbols consistent)
    s = unicodedata.normalize("NFKC", s)
    # Collapse multiple spaces/newlines into single space
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def is_message_sent(driver, expected_text: str) -> bool:
    try:
        chat_elems = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, 'div[role="presentation"] > span[dir="auto"]')
            )
        )

        if not chat_elems:
            print(f"⚠️ No chat elements found")
            return False

        expected_msg = normalize_text(expected_text)

        # Check last 3 messages instead of just the last one
        for elem in reversed(chat_elems[-3:]):
            msg = normalize_text(elem.text)
            if msg == expected_msg or msg.startswith(expected_msg):
                return True

        print(f"❌ Message not found in last 3 chat elements.")
        return False

    except Exception as e:
        print(f"⚠️ Could not verify message: {e}")
        return False


def verify_message_sent(driver, username, message_text, observer) -> tuple[bool, str]:
    """
    Verify if a message was successfully sent after pressing RETURN.
    
    Returns:
        tuple[bool, str]: (success, reason)
            - (True, "sending_indicator")  → SVG appeared and disappeared cleanly
            - (True, "found_in_chat")      → Found in chat after refresh
            - (False, "failed_svg")        → Instagram showed failure icon (emergency)
            - (False, "not_in_chat")       → Not found in chat after refresh
            - (False, "error")             → Unexpected exception
    """
    try:
        # ── CHECK 1: Sending indicator (SVG spinner) ──────────────────────────
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "svg[aria-label='IGD message sending status icon']")
                )
            )
            print("⏳ Sending indicator detected, waiting for it to clear...")

            # ── CHECK 2 (inline): While waiting for spinner to go, watch for failure SVG ──
            # Poll every 500ms instead of a blind until_not, so we can catch failure icon
            deadline = time.time() + 10  # max 10s for spinner to disappear
            while time.time() < deadline:
                # Check for failure SVG first (emergency)
                failed_svgs = driver.find_elements(
                    By.CSS_SELECTOR, "svg[aria-label='Failed to send']"
                )
                if failed_svgs:
                    print(f"🚨 EMERGENCY: Instagram reported failed to send to @{username}")
                    return False, "failed_svg"

                # Check if spinner is gone
                sending_svgs = driver.find_elements(
                    By.CSS_SELECTOR, "svg[aria-label='IGD message sending status icon']"
                )
                if not sending_svgs:
                    print(f"✅ Message sent to @{username}: {message_text}")
                    return True, "sending_indicator"

                time.sleep(0.5)

            # Spinner never disappeared in time — fall through to chat check
            print("⚠️ Sending indicator didn't clear in time, falling back to chat check...")

        except TimeoutException:
            # Spinner never appeared — not necessarily bad, fall through
            print("⚠️ No sending indicator appeared, checking for failure SVG...")

            # ── CHECK 2 (standalone): Spinner never showed, but failure might have ──
            failed_svgs = driver.find_elements(
                By.CSS_SELECTOR, "svg[aria-label='Failed to send']"
            )
            if failed_svgs:
                print(f"🚨 EMERGENCY: Failed to send icon found for @{username}")
                return False, "failed_svg"

        # ── CHECK 3: Scan chat — refresh only if message isn't already visible ──
        print("🔍 Checking chat before deciding to refresh...")

        # ✅ Message already in DOM — no refresh needed, saves full page reload
        if is_message_sent(driver, message_text):
            print(f"✅ Message confirmed in chat for @{username}: {message_text}")
            return True, "found_in_chat"

        # ✅ Not visible yet — now a refresh is justified to get latest state
        print("🔄 Message not visible yet, refreshing to confirm...")
        observer.health_monitor.revive_driver("refresh")
        time.sleep(3)

        if is_message_sent(driver, message_text):
            print(f"✅ Message confirmed in chat after refresh for @{username}: {message_text}")
            return True, "found_in_chat"
        else:
            print(f"❌ Message NOT found in chat for @{username}: {message_text}")
            return False, "not_in_chat"

    except Exception as e:
        print(f"❌ Unexpected error during verification for @{username}: {e}")
        return False, "error"


def send_message_to_user(driver, username, messages, human_mouse: HumanMouseBehavior,  human_typing: HumanTypingBehavior, observer: ScreenObserver, webhook: WebhookUtils):
    """
    Send a message to a user from their profile page.

    Args:
        driver: Selenium WebDriver instance
        username: Username to send message to
        message_text: Message content
        basicUtils: BasicUtils instance
        human_mouse: HumanMouseBehavior instance

    Returns:
        bool: True if message sent successfully, False otherwise
    """
    try:
        for message_text in messages:
            retries = 0
            sent = False

            while retries <= MESSAGE_MAX_RETRIES and not sent:
                try:
                    # Focus input
                    message_input = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div[role='textbox']"))
                    )
                    try:
                        val1 = human_mouse.human_like_move_to_element(message_input, click=True)
                        val2 = human_typing.human_like_type(message_input, message_text)

                        if not (val1 and val2):
                            raise Exception("Failed to interact with message input")
                        
                    except Exception as e:
                        print("♻️ Message input went stale, refreshing and retrying...")
                        observer.health_monitor.revive_driver("screenshot")
                        time.sleep(3)

                        message_input = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='textbox']"))
                        )
                        val1 = human_mouse.human_like_move_to_element(message_input, click=True)
                        val2 = human_typing.human_like_type(message_input, message_text)

                        if not (val1 and val2):
                            raise Exception("Failed to interact with message input")

                    time.sleep(1.5)
                    observer.health_monitor.revive_driver("screenshot")
                    message_input.send_keys(Keys.RETURN)

                    success, reason = verify_message_sent(driver, username, message_text, observer)

                    if success:
                        sent = True

                    elif reason == "failed_svg":
                        # Emergency — Instagram explicitly rejected it, stop immediately
                        # webhook.update_campaign_status("failed_dm_flag_by_instagram", {
                        #     "campaign_id": webhook.attributes.get("campaign_id", None)
                        # })
                        return False

                    else:
                        # Not confirmed — retry
                        retries += 1
                        if retries <= MESSAGE_MAX_RETRIES:
                            print(f"🔄 Retrying DM to @{username}... (Attempt {retries})")
                            time.sleep(2)
                        else:
                            print(f"❌ Failed to send after {MESSAGE_MAX_RETRIES} retries.")
                            return False

                except RuntimeError as r:
                    raise

                except Exception as inner_e:
                    print(
                        f"❌ Error sending message '{message_text}' to @{username}: {inner_e}")
                    return False

        return True

    except RuntimeError as r:
        raise

    except Exception as e:
        print(f"❌ Fatal error while sending messages to @{username}: {e}")
        return False


def check_if_existing_messages_are_present(driver,username:str, observer: ScreenObserver):
    """
    Check if user is new or has talked priviously.

    Args:
        driver: Selenium WebDriver instance
        username: Username to send followup to
        observer: ScreenObserver instance

    Returns: 
        bool: If the user has already talked or not
    """
    try:
        # Wait for chat elements to load
        observer.health_monitor.revive_driver("click_body")
        time.sleep(3)

        # old reply check method --------
        chat_containers = driver.find_elements(
            By.CSS_SELECTOR,
            'div[data-virtualized="false"]'
        )

        # new reply check method (check for spans with text message either sender or reciever)
        message_spans = driver.find_elements(By.CSS_SELECTOR,'div[role="presentation"] > span[dir="auto"]')

        # if no chat containers or message spans are found then return False
        if (not chat_containers or len(chat_containers) == 0) and (not message_spans or len(message_spans) == 0):
            return False

        return True

    except Exception as e:
        print(f"❌ Error in checking previous message for @{username}: {str(e)}")
        return False


def check_for_reply(driver, username,  observer: ScreenObserver, prev_text=None):
    """
    Check if user has replied in DM.

    Args:
        driver: Selenium WebDriver instance
        username: Username to send followup to
        observer: ScreenObserver instance

    Returns: 
        bool: If the user has replied
    """
    try:
        # Wait for chat elements to load
        observer.health_monitor.revive_driver("click_body")
        time.sleep(3)

        # ---------- Old method ----------
        chat_containers = driver.find_elements(
            By.CSS_SELECTOR,
            'div[data-virtualized="false"]'
        )

        if chat_containers:
            last_elem = chat_containers[-1]
            anchors = last_elem.find_elements(
                By.CSS_SELECTOR,
                f'a[href*="/{username}"]'
            )
            if anchors:
                print(f"✅ @{username} has already replied.")
                return True

        reply_check_xpath = ''

        if prev_text is not None:
            found = scroll_until_prev_text_visible(driver, prev_text)
            if not found:
                scroll_to_bottom_message_container(driver)  # ← restore position before fallback
                prev_text = None

        if prev_text is not None:
            reply_check_xpath = f'//div[@role="none" and ../../preceding-sibling::*[.//a[@role="link" and contains(@href,"/{username}")]] and preceding::div[@role="none"][.//span[@dir="auto" and contains(.,"{prev_text}")]]] //span[@dir="auto"]'
        else:
            reply_check_xpath = f'//div[@role="none" and ../../preceding-sibling::*[.//a[@role="link" and contains(@href,"/{username}")]]] //span[@dir="auto"]'

        # check by new method ---------------------
        message_spans = driver.find_elements(
            By.XPATH,
            reply_check_xpath
        )
        
        if message_spans:
            print(f"✅ @{username} has already replied.")
            return True

        print(f"ℹ️ @{username} has not replied.")
        return False

    except Exception as e:
        print(f"❌ Error in reply check for @{username}: {str(e)}")
        return False


def scroll_until_prev_text_visible(driver, prev_text: str, max_scrolls: int = 15) -> bool:
    """
    Scrolls up incrementally in small steps until prev_text appears in DOM,
    then scrolls the element into view centered in the viewport.
    """
    SCROLL_CONTAINER_XPATH = '//div[@data-pagelet="IGDMessagesList"]/div'

    try:
        container = driver.find_element(By.XPATH, SCROLL_CONTAINER_XPATH)
    except Exception:
        print("❌ Could not find DM scroll container")
        return False

    # check if already in DOM before scrolling at all
    matches = driver.find_elements(
        By.XPATH,
        f'//span[@dir="auto" and contains(.,"{prev_text}")]'
    )
    if matches:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            matches[0]
        )
        time.sleep(0.4)
        return True

    for attempt in range(max_scrolls):
        driver.execute_script(
            "arguments[0].scrollTop -= 300;",
            container
        )
        time.sleep(0.8)  # wait for instagram to lazy-load newly visible messages

        matches = driver.find_elements(
            By.XPATH,
            f'//span[@dir="auto" and contains(.,"{prev_text}")]'
        )
        if matches:
            print(f"Found prev_text '{prev_text}' after {attempt + 1} scroll(s)")
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
                matches[0]
            )
            time.sleep(0.4)
            return True

    print(f"⚠️ prev_text '{prev_text}' not found after {max_scrolls} scrolls, falling back")
    return False

def scroll_to_bottom_message_container(driver) -> None:
    """Scrolls the DM container back to the bottom (most recent messages)."""
    SCROLL_CONTAINER_XPATH = '//div[@data-pagelet="IGDMessagesList"]/div'
    try:
        container = driver.find_element(By.XPATH, SCROLL_CONTAINER_XPATH)
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight;",
            container
        )
        time.sleep(0.4)  # let it settle
    except Exception:
        logging.warning("Could not scroll DM container to bottom")

def message_users_from_list(driver, usernames_list, message_text, delay_range=(30, 60)):
    """
    Main function to search and message a list of users.

    Args:
        driver: Selenium WebDriver instance
        usernames_list: List of usernames to message
        message_text: Message to send
        delay_range: Tuple of (min, max) seconds between messages

    Returns:
        tuple: (successful_messages, failed_users)
    """
    print("🚀 Starting Instagram messaging automation...")

    # Validate inputs
    if not usernames_list:
        print("❌ No usernames provided!")
        return [], []

    if not message_text.strip():
        print("❌ No message text provided!")
        return [], []

    # Remove duplicates and clean usernames
    clean_usernames = list(set([username.strip().replace(
        '@', '') for username in usernames_list if username.strip()]))

    print(f"📝 Processing {len(clean_usernames)} unique usernames...")
    print(f"💬 Message: {message_text}")

    return search_and_message_users(driver, clean_usernames, message_text, delay_range)


def random_warmup(driver, observer: ScreenObserver):
    """
    Function that warmup randomly.

    Args:
        driver: Selenium WebDriver instance
        observer: ScreenObserver instance

    """
    try:
        warmup_type = random.randint(1, 3)

        time.sleep(3)

        browse_explore_page(driver, observer)
        # if (warmup_type == 1):
        #     explore_reels_randomly(
        #         driver, observer, count=random.randint(1, 3))
        # elif (warmup_type == 2):
        # else:
        #     print("Viewing stories")
        #     browse_explore_page(driver, observer)

    except Exception as e:
        print("❌ Found error in warming up")


def is_page_healthy(driver) -> bool:
    """
    Returns True if the page is responsive — no refresh needed.
    Checks JS execution, document readyState, and URL validity.
    """
    try:
        ready = driver.execute_script("return document.readyState")
        if ready != "complete":
            return False

        current_url = driver.current_url
        if not current_url or current_url in ("about:blank", "data:,"):
            return False

        # Quick JS ping — if this throws, the page is hung
        driver.execute_script("return 1")
        return True

    except Exception:
        return False

