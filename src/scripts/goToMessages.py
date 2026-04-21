from utils.scrapping.BandwidthTracker import BandwidthTracker
import time
import random
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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

    seen = {}
    for msg in messages_to_send:
        seen[msg['username']] = msg
    messages_to_send = list(seen.values())
    instgram_page_error_count = 0
    instgram_page_error_limit = 4

    # ✅ Track who was messaged THIS session
    already_messaged_this_session = set()

    # message sending loop ---------------------------------------
    for i, message in enumerate(messages_to_send):
        print(
            f"\n📝 Processing user {i+1}/{len(messages_to_send)}: @{message['username']}")

        username = message['username']
        messages = message.get('messages', None)
        message_type = message['type']

        # ✅ Skip if already messaged in this session
        if username in already_messaged_this_session:
            print(f"⚠️ Skipping @{username} — already messaged this session")
            continue

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


        try:
            # Search for the username
            search_fn = search_user_via_profile if message_type == "MESSAGE" else search_user


            # ✅ If type is FOLLOWUP or REPLY_CHECK, ensure we're on /direct/ before searching
            if message_type in ("FOLLOWUP", "REPLY_CHECK"):
                current_url = driver.current_url
                # ✅ Close any leftover open search sidebar before proceeding
                try:
                    close_btn = driver.find_element(
                        By.XPATH,
                        "//div[@aria-label='Close' and @role='button']"
                    )
                    if close_btn.is_displayed():
                        print(f"⚠️ Search sidebar still open, closing it...")
                        human_mouse.human_like_move_to_element(close_btn, click=True)
                        time.sleep(1.5)
                        print(f"✅ Sidebar closed.")
                except NoSuchElementException:
                    pass  # No open sidebar, all good

                if "/direct/" not in current_url:
                    print(f"⚠️ Not on /direct/ page (currently: {current_url}), navigating to inbox first...")
                    basicUtils.click_anchor_by_href("/direct/inbox/")
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.url_contains("/direct/inbox")
                        )
                        time.sleep(3)
                    except TimeoutException:
                        print(f"⚠️ Failed to navigate to inbox, attempting recovery...")
                        observer.health_monitor.revive_driver("screenshot")
                        time.sleep(3)

            if search_fn(driver, username, human_mouse, human_typing,bandwidthTracker, observer):
                print(f"✅ User @{username} found!")
                time.sleep(2)

                bandwidthTracker.set_action("Sending message to user")

                # ── Check for Instagram "Something isn't working." error ──────
                try:
                    error_banner = driver.find_element(
                        By.XPATH,
                        "//span[@dir='auto']//span[contains(text(), concat('Something isn', \"'\", 't working'))]"
                    )
                    if error_banner and error_banner.is_displayed():
                        print(f"⚠️ Instagram page error detected for @{username}, text: {error_banner.text}, skipping.")
                        instgram_page_error_count += 1
                        
                        if instgram_page_error_count == instgram_page_error_limit:
                            webhook.update_campaign_status("instagram_page_error", {
                                "campaign_id": webhook.attributes.get("campaign_id", None),
                                "page": "Messaging Page"
                            })
                            raise RuntimeError(f"Instagram page error limit reached, max {instgram_page_error_limit} errors encountered")

                        continue
                except NoSuchElementException:
                    pass

                if message_type == "MESSAGE":
                    try:
                        if (send_to_new_users_only and check_if_existing_messages_are_present(driver, username, observer)):
                            webhook.update_campaign_status("sent_dm", {
                                "campaign_id": webhook.attributes.get("campaign_id", None),
                                "username": username,
                                "data": {"already":True},
                                "type": "MESSAGE",
                                "failed":True
                            })
                            print( f"❌ Username @{username} has previous chats with the ig user, hence marking as failed")

                        elif send_message_to_user(driver, username, messages, human_mouse, human_typing, observer, webhook):
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
                                    "type": "REPLY_CHECK"
                                })

                        else:
                            raise Exception( f"❌ Username @{username}, messaging failed")

                    except Exception as e:
                        print(f"Error: {str(e)}")
                        webhook.update_campaign_status("sent_dm", {
                            "campaign_id": webhook.attributes.get("campaign_id", None),
                            "username": username,
                            "data": {},
                            "type": "MESSAGE",
                            "failed":True
                        })
                        print(f"❌ Failed to send message to @{username}")

                elif message_type == "FOLLOWUP":
                    try:
                        prevmsg = message.get("prevText")
                        replied = check_for_reply(driver, username, observer, prevmsg)
                        time.sleep(3)

                        # user has replied do not followup -------
                        if replied:
                            webhook.update_campaign_status("sent_dm", {
                                "campaign_id": webhook.attributes.get("campaign_id", None),
                                "username": username,
                                "data": {
                                    "replied": True
                                },
                                "type": "REPLY_CHECK"
                            })

                        else:
                            if send_message_to_user(driver, username, messages, human_mouse, human_typing, observer, webhook):
                                successful_messages.append(username)
                                webhook.update_campaign_status("sent_dm", {
                                    "campaign_id": webhook.attributes.get("campaign_id", None),
                                    "username": username,
                                    "data": {
                                        "serial": message["serial"],
                                    },
                                    "type": "FOLLOWUP"
                                })
                                print(f"✅ Followup sent to @{username}")

                            else:
                                raise Exception( f"❌ Username @{username}, followup messaging failed")

                    except Exception as e:
                            print(f"Error: {str(e)}")
                            webhook.update_campaign_status("sent_dm", {
                                "campaign_id": webhook.attributes.get("campaign_id", None),
                                "username": username,
                                "data": {
                                    "serial": message["serial"],
                                },
                                "type": "FOLLOWUP",
                                "failed":True
                            })
                            print(f"❌ Failed to send followup to @{username}")
                            
                    
                elif message_type == "REPLY_CHECK":
                    try:
                        prevmsg = message.get("prevText")
                        replied = check_for_reply(driver, username, observer, prevmsg)
                        time.sleep(3)

                        # user has replied do not followup -------    
                        if replied:
                            webhook.update_campaign_status("sent_dm", {
                                "campaign_id": webhook.attributes.get("campaign_id", None),
                                "username": username,
                                "data": {
                                    "replied": True
                                },
                                "type": "REPLY_CHECK"
                            })
                            print(f"✅ User @{username} has replied")
                        else:
                            webhook.update_campaign_status("sent_dm", {
                                "campaign_id": webhook.attributes.get("campaign_id", None),
                                "username": username,
                                "data": {
                                    "replied": False
                                },
                                "type": "REPLY_CHECK"
                            })
                            print(f"❌ User @{username} has not replied")
                    except Exception as e:
                        print(f"Error: {str(e)}")
                        pass

            else:
                webhook.update_campaign_status("sent_dm", {
                    "campaign_id": webhook.attributes.get("campaign_id", None),
                    "username": username,
                    "data": {},
                    "type": message_type,
                    "failed": True
                })
                print(f"❌ User @{username} not found, skipping...")

            already_messaged_this_session.add(username)

        except RuntimeError as r:
            raise

        except Exception as e:
            print(f"❌ Error processing @{username}: {str(e)}")

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

    if successful_messages:
        print(
            f"✅ Successful messages sent to: {', '.join(successful_messages)}")


    return successful_fresh_dms, successful_messages


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


def search_user_via_profile(driver, username: str, human_mouse: HumanMouseBehavior, human_typing: HumanTypingBehavior, bandwidthTracker: BandwidthTracker, observer: ScreenObserver, retry_delay: float = 2.0):
    attempt = 0
    bandwidthTracker.set_action("Searching for user via profile")

    while attempt < USER_MAX_RETRIES:
        try:
            observer.health_monitor.revive_driver("click_body")
            time.sleep(1)

            # ── STEP 1 & 2: Ensure search panel is open and type username ─────
            search_panel_input = (By.CSS_SELECTOR, "input[aria-label='Search input'][placeholder='Search']")

            panel_already_open = False
            try:
                panel_already_open = bool(driver.find_elements(By.CSS_SELECTOR, "input[aria-label='Search input'][placeholder='Search']"))
            except Exception:
                panel_already_open = False

            if not panel_already_open:
                # Panel not open — click the first Search SVG to open it
                search_svgs = driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Search']")
                if not search_svgs:
                    raise Exception("No Search SVG found on page")

                human_mouse.human_like_move_to_element(search_svgs[0], click=True)
                time.sleep(1.5)

                try:
                    WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable(search_panel_input)
                    )
                except TimeoutException:
                    print("⚠️ Search panel did not open, attempting revive...")
                    observer.health_monitor.revive_driver("click_body")
                    time.sleep(1.5)
                    WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable(search_panel_input)
                    )

            # Panel is open — click input and type
            human_mouse.human_like_move_to_element(search_panel_input, click=True)
            time.sleep(1)
            human_typing.human_like_type(search_panel_input, text=username, clear_field=True)

            # Extra wait for special usernames (leading _ or containing .)
            has_special = username.startswith('_') or '.' in username
            time.sleep(4.0 if has_special else 2.5)

            # ✅ Verify search results actually loaded, with progressive recovery
            results_xpath = "//div[contains(@class,'html-div')]//a[@role='link']"
            results_loaded = False

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, results_xpath))
                )
                results_loaded = True
            except TimeoutException:
                pass

            if not results_loaded:
                print(f"⚠️ Search results did not load for @{username} — attempt {attempt+1}, trying recovery...")
                if attempt == 0:
                    # 1st failure: close search bar and reopen it
                    print(f"🔄 Recovery 1: Closing and reopening search panel...")
                    try:
                        close_btn = driver.find_element(By.XPATH, "//div[@aria-label='Close' and @role='button']")
                        if close_btn.is_displayed():
                            human_mouse.human_like_move_to_element(close_btn, click=True)
                            time.sleep(1.5)
                    except NoSuchElementException:
                        pass
                
                elif attempt == 1:
                    # 2nd failure: refresh the page
                    print(f"🔄 Recovery 2: Refreshing page...")
                    observer.health_monitor.revive_driver("refresh")
                    time.sleep(4)

                else:
                    # 3rd+ failure: give up on this user
                    print(f"❌ Search results never loaded for @{username} after {attempt+1} attempts, skipping...")
                    attempt += 1
                    time.sleep(retry_delay)
                    continue
                
                attempt += 1
                time.sleep(retry_delay)
                continue

            # ── STEP 3: Find profile link in results, scroll if needed ────────
            profile_link_xpath = f"//a[@href='/{username}/' and @role='link'] | //a[@href='/{username}' and @role='link']"

            user_result = None
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.XPATH, profile_link_xpath))
                )
                user_result = driver.find_element(By.XPATH, profile_link_xpath)
            except TimeoutException:
                print(f"⚠️ Profile link not immediately visible, scrolling results...")

            if user_result is None:
                observer.health_monitor.revive_driver("screenshot")
                time.sleep(1.5)
                matches = driver.find_elements(By.XPATH, profile_link_xpath)
                user_result = matches[0] if matches else None

            if user_result is None:
                print(f"⚠️ Attempt {attempt+1}: No profile link found for @{username}")
                attempt += 1
                time.sleep(retry_delay)
                continue

            human_mouse.human_like_move_to_element(user_result, click=True)
            time.sleep(2)

            # ── STEP 4: Wait for profile page to load ─────────────────────────
            try:
                WebDriverWait(driver, 10).until(
                    EC.url_contains(f"/{username}/")
                )
                time.sleep(2)
            except TimeoutException:
                print(f"⚠️ Profile page did not load for @{username}, reviving...")
                observer.health_monitor.revive_driver("click_body")
                time.sleep(3)
                try:
                    WebDriverWait(driver, 10).until(
                        EC.url_contains(f"/{username}/")
                    )
                except TimeoutException:
                    print(f"⚠️ Attempt {attempt+1}: Profile still not loaded for @{username}")
                    attempt += 1
                    time.sleep(retry_delay)
                    continue

            # ── STEP 5: Detect public vs private account ───────────────────────
            message_btn_xpath = "//div[@role='button' and normalize-space(text())='Message']"
            options_svg_css_selectors = "svg[aria-label='Options']"

            message_btn = None
            is_private = False

            observer.health_monitor.revive_driver("screenshot")
            time.sleep(3)

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, message_btn_xpath))
                )
                message_btn = driver.find_element(By.XPATH, message_btn_xpath)
            except TimeoutException:
                print(f"⚠️ No Message button found for @{username}, checking if private...")
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, options_svg_css_selectors))
                    )
                    is_private = True
                except TimeoutException:
                    print(f"⚠️ Neither Message button nor Options SVG found for @{username}")

                    if attempt < USER_MAX_RETRIES:
                        observer.health_monitor.revive_driver("refresh")
                        time.sleep(10)

                    attempt += 1
                    time.sleep(retry_delay)
                    continue

            # ── STEP 6: Click Message or Options → Message ────────────────────
            if not is_private:
                human_mouse.human_like_move_to_element(message_btn, click=True)
                try:
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
                    )
                    dialog_msg_btn = driver.find_element(
                        By.XPATH, "//div[@role='dialog']//button[contains(text(),'message request')]"
                    )
                    human_mouse.human_like_move_to_element(dialog_msg_btn, click=True)
                except TimeoutException:
                    print(f"⚠️ Dialog did not appear for public account @{username}, maybe the sidebar has appeared instead")

            else:
                options_svg = driver.find_element(By.CSS_SELECTOR, options_svg_css_selectors)
                human_mouse.human_like_move_to_element(options_svg, click=True)
                time.sleep(1.5)

                try:
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
                    )
                    dialog_msg_btn = driver.find_element(
                        By.XPATH, "//div[@role='dialog']//button[contains(text(),'message')]"
                    )
                    human_mouse.human_like_move_to_element(dialog_msg_btn, click=True)
                    time.sleep(10)
                except TimeoutException:
                    print(f"⚠️ Dialog did not appear for private account @{username}")
                    attempt += 1
                    time.sleep(retry_delay)
                    continue

            # ── STEP 7: Verify landed on /direct/t/ or fallback to sidebar ────
            try:
                WebDriverWait(driver, 8).until(
                    EC.url_contains("/direct/t/")
                )
                print(f"✅ Landed on DM thread for @{username}")
                time.sleep(2)
                return True

            except TimeoutException:
                # ✅ Sidebar fallback ONLY for public accounts
                if not is_private:
                    print(f"⚠️ Did not land on /direct/t/, checking for sidebar...")
                    try:
                        WebDriverWait(driver, 6).until(
                            EC.presence_of_element_located((
                                By.XPATH,
                                "//div[contains(@aria-label,'Conversation with')]"
                            ))
                        )

                        try:
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((
                                    By.XPATH,
                                    f"//div[contains(@aria-label,'Conversation with')]//span[contains(text(),'{username}')]"
                                ))
                            )
                            print(f"✅ Username @{username} confirmed in conversation.")

                        except TimeoutException:
                            print(f"⚠️ Wrong conversation loaded (not @{username}), closing sidebar and retrying...")
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

                        expand_svg = driver.find_element(By.CSS_SELECTOR, "svg[aria-label='Expand']")
                        human_mouse.human_like_move_to_element(expand_svg, click=True)
                        time.sleep(8)

                        WebDriverWait(driver, 6).until(
                            EC.url_contains("/direct/t/")
                        )
                        print(f"✅ Landed on DM thread via Expand for @{username}")
                        time.sleep(2)
                        return True

                    except Exception as sidebar_e:
                        print(f"⚠️ Sidebar fallback failed for @{username}: {sidebar_e}")
                        attempt += 1
                        time.sleep(retry_delay)
                        continue

                else:
                    # ✅ Private account — no sidebar expected, just retry
                    print(f"⚠️ Private account @{username} did not land on /direct/t/, retrying...")
                    attempt += 1
                    time.sleep(retry_delay)
                    continue
        
        except Exception as e:
            print(f"❌ Attempt {attempt+1}: Error in profile search for @{username}: {str(e)}")
            attempt += 1
            time.sleep(retry_delay)

    print(f"❌ Failed to reach DM thread for @{username} after {USER_MAX_RETRIES} attempts")
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
        print("Could not scroll DM container to bottom")

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

