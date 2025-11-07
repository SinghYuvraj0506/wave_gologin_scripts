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
from scripts.exploreReel import explore_reels_randomly
from scripts.browseExplore import browse_explore_page
import unicodedata
import re

MESSAGE_MAX_RETRIES = 2
USER_MAX_RETRIES = 2

def search_and_message_users(driver, messages_to_send, observer: ScreenObserver, webhook: WebhookUtils, delay_between_messages=(30, 50)):
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
    time.sleep(2)

    observer.health_monitor.revive_driver("screenshot")

    # Check if we're on a valid user profile
    try:
        WebDriverWait(driver, 10).until(
            EC.url_contains("/direct/inbox/")
        )
    except TimeoutException:
        try:
            observer.health_monitor.revive_driver("refresh")
            time.sleep(2)
            observer.health_monitor.revive_driver("click_body")
            WebDriverWait(driver, 12).until(
                EC.url_contains("/direct/inbox/")
            )
        except Exception as e:
            raise Exception("Page not clicked")

    print(f"🔍 Starting to search and message {len(messages_to_send)} users...")
    time.sleep(4)

    # 👇 Pick a random iteration for warmup , no warmuo befire the last iterations
    warmup_index = random.randint(-(len(messages_to_send)*2) +
                                  1, len(messages_to_send) - 2)

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
            try:
                observer.health_monitor.revive_driver("screenshot")
                WebDriverWait(driver, 7).until(
                    EC.url_contains("/direct/inbox/")
                )
            except TimeoutException:
                try:
                    observer.health_monitor.revive_driver("refresh")
                    WebDriverWait(driver, 10).until(
                        EC.url_contains("/direct/inbox/")
                    )
                except Exception as e:
                    raise Exception("Page not clicked")

            time.sleep(3)

        username = message['username']
        messages = message['messages']
        message_type = message['type']

        try:
            # Search for the username
            if search_user(driver, username, human_mouse, human_typing, observer):
                print(f"✅ User @{username} found!")

                if message_type == "MESSAGE":
                    if send_message_to_user(driver, username, messages, human_mouse, human_typing, observer):
                        successful_messages.append(username)
                        successful_fresh_dms += 1
                        webhook.update_campaign_status("sent_dm", {
                            "campaign_id": webhook.attributes.get("campaign_id", None),
                            "username": username,
                            "data": {},
                            "type": "MESSAGE"
                        })
                        print(f"✅ Message sent to @{username}")

                    else:
                        raise Exception(
                            f"❌ Failed to send message to @{username}")

                else:
                    replied = check_for_reply(driver, username, observer)
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
                        if send_message_to_user(driver, username, messages, human_mouse, human_typing, observer):
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


def search_user(driver, username: str, human_mouse: HumanMouseBehavior, human_typing: HumanTypingBehavior, observer: ScreenObserver, retry_delay: float = 2.0):
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

            # Click search bar
            observer.health_monitor.revive_driver("scroll")

            search_input = (By.CSS_SELECTOR, "input[placeholder*='Search']")
            human_mouse.human_like_move_to_element(search_input, click=True)
            time.sleep(1.5)

            elem = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(search_input))
            human_typing.human_like_type(
                search_input, text=username, clear_field=True)

            time.sleep(2.5)

            try:
            # Wait for search results to appear and find the exact user
                observer.health_monitor.revive_driver("screenshot")
                user_result = (By.XPATH, f"//h2[normalize-space(text())='More accounts']/following::span[text()='{username}']")
                human_mouse.human_like_move_to_element(user_result, click=True)
                time.sleep(2)
                observer.health_monitor.revive_driver("refresh")
                try:
                    observer.health_monitor.revive_driver("click_body")
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located(
                            (By.XPATH, f"//span[contains(text(),'{username} · Instagram')]"))
                    )
                    return True
                except TimeoutException:
                    try:
                        observer.health_monitor.revive_driver("screenshot")
                        WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located(
                                (By.XPATH, f"//a[@href='/{username}/' and @role='link']"))
                        )
                        return True
                    except TimeoutException:
                        pass

            except TimeoutException:
                print(f"⚠️ Attempt {attempt+1}: No exact match found for @{username}")

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
                (By.CSS_SELECTOR, 'div[data-virtualized="false"]')
            )
        )

        if not chat_elems:
            print(f"⚠️ No chat elements found")
            return False

        last_elem = chat_elems[-1]
        last_msg = normalize_text(last_elem.text)
        expected_msg = normalize_text(expected_text)

        # Exact match OR last message starts with expected (for emojis/trailing chars)
        if last_msg == expected_msg or last_msg.startswith(expected_msg):
            return True
        else:
            print(
                f"❌ Last message mismatch.\nExpected: {expected_msg}\nFound: {last_msg}")
            return False

    except Exception as e:
        print(f"⚠️ Could not verify message: {e}")
        return False


def send_message_to_user(driver, username, messages, human_mouse: HumanMouseBehavior,  human_typing: HumanTypingBehavior, observer: ScreenObserver):
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
                        human_mouse.human_like_move_to_element(message_input, click=True)
                        human_typing.human_like_type(message_input, message_text)
                    except Exception as e:
                        print("♻️ Message input went stale, refreshing and retrying...")
                        observer.health_monitor.revive_driver("refresh")
                        time.sleep(2)

                        message_input = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='textbox']"))
                        )
                        human_mouse.human_like_move_to_element(message_input, click=True)
                        human_typing.human_like_type(message_input, message_text)

                    time.sleep(1.5)
                    observer.health_monitor.revive_driver("screenshot")
                    message_input.send_keys(Keys.RETURN)

                    # Wait for sending indicator
                    try:
                        WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR,
                                 "svg[aria-label='IGD message sending status icon']")
                            )
                        )
                        print(
                            "⏳ Sending indicator detected, waiting for completion...")

                        WebDriverWait(driver, 10).until_not(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR,
                                 "svg[aria-label='IGD message sending status icon']")
                            )
                        )
                        print(f"✅ Message sent to @{username}: {message_text}")
                        sent = True

                    except TimeoutException:
                        print("⚠️ No sending indicator, checking chat...")
                        if is_message_sent(driver, message_text):
                            print(
                                f"✅ Message confirmed in chat to @{username}: {message_text}")
                            sent = True
                        else:
                            retries += 1
                            if retries <= MESSAGE_MAX_RETRIES:
                                print(
                                    f"🔄 Retrying DM to @{username} after refresh... (Attempt {retries})")
                                observer.health_monitor.revive_driver(
                                    "refresh")
                                time.sleep(5)
                            else:
                                print(
                                    f"❌ Failed to send message after {MESSAGE_MAX_RETRIES} retries.")
                                return False

                except Exception as inner_e:
                    print(
                        f"❌ Error sending message '{message_text}' to @{username}: {inner_e}")
                    return False

        return True

    except Exception as e:
        print(f"❌ Fatal error while sending messages to @{username}: {e}")
        return False


def check_for_reply(driver, username, observer: ScreenObserver):
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

        chat_elems = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, 'div[data-virtualized="false"]')
            )
        )

        if not chat_elems:
            print(f"⚠️ No chat elements found for @{username}")
            return False

        # Get the last chat element
        last_elem = chat_elems[-1]

        # Check if last message has an anchor tag with username
        try:
            anchor = last_elem.find_element(
                By.CSS_SELECTOR, f'a[href*="{username}"]')
            if anchor:
                print(f"✅ @{username} has already replied. Skipping followup.")
                return True
        except:
            # No anchor found → means no reply yet
            print(f"ℹ️ @{username} has not replied. Sending followup...")

        return False

    except Exception as e:
        print(f"❌ Error in followup check/send for @{username}: {str(e)}")
        return False


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
