from utils.scrapping.ScreenObserver import ScreenObserver
import time
from scripts.login import insta_login
from scripts.exploreReel import explore_reels_randomly
from scripts.browseExplore import browse_explore_page
from scripts.goToMessages import search_and_message_users
from scripts.goToProfile import goto_profile_and_save_image
import logging
from selenium.webdriver.common.by import By
from gologinHandlers import GologinHandler
from utils.WebhookUtils import WebhookUtils
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import json
import sys


class MainExecutor:
    def __init__(self, webhook: WebhookUtils):
        self.profile_id = webhook.profile_id
        self.proxy_country = webhook.proxy_country
        self.proxy_city = webhook.proxy_city
        self.proxy_city_fallbacks = webhook.proxy_city_fallbacks
        self.session_id = webhook.proxy_session_id
        self.task_type = webhook.task_type
        self.logged_in = False
        self.gologin = None
        self.observer = None
        self.initialized = False
        self.cookies = None
        self.webhook = webhook
        self.need_task_retry = False

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def observer_callback_handler(self, event_type: str, data):
        """Callback function to handle any unexpected events like 'url_change', 'dialog_detected', 'action_required'"""
        print(f"👮 Observer Event: {event_type} Detected")
        print(f"Data: {json.dumps(data, indent=2)}")

        if event_type == "action_required":
            self.webhook.update_account_status(event="login_manual_interuption_required", payload={
                                               "metadata": data, "account_id": self.webhook.account_id})
            self.webhook.update_task_status("task_failed")
            self.cleanup()
            print("Manual Interuption Required, Stopping the script to run further")
            sys.exit(1)

    def initialize_session(self):
        """Initialize GoLogin session and driver"""
        try:
            self.logger.info(
                f"Initializing session for profile: {self.profile_id}")

            # Initialize GoLogin handler
            self.gologin = GologinHandler(
                profile_id=self.profile_id,
                proxy_country=self.proxy_country,
                proxy_city=self.proxy_city,
                proxy_city_fallbacks=self.proxy_city_fallbacks,
                session_id=self.session_id,
                account_id=self.webhook.account_id
            )

            self.profile_id = self.gologin.profile_id

            self.gologin.connect_gologin_session()

            # Get driver from gologin handler
            self.driver = self.gologin.driver

            # Start screen observer
            self.observer = ScreenObserver(
                self.driver, callback_function=self.observer_callback_handler)
            self.observer.start_monitoring()

            # Force initial revival
            self.observer.health_monitor.revive_driver("scroll")

            self.initialized = True
            self.logger.info("✅ Session initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize session: {e}")
            return False

    def check_login_status(self):
        try:
            if not self.driver:
                return False

            print("Checking login status...")

            # Set shorter page load timeout to prevent hanging
            original_timeout = self.driver.timeouts.page_load
            self.driver.set_page_load_timeout(20)  # Shorter timeout

            try:
                self.driver.get("https://www.instagram.com/")
            except Exception as e:
                if "timeout" in str(e).lower():
                    print("⚠️ Page load timeout - attempting recovery")
                    # Don't fail immediately, try to work with partial load
                else:
                    raise e

            # Immediate health check after page load
            try:
                self.driver.execute_script("return document.readyState;")
            except:
                print("🔄 Driver unresponsive - attempting revival")
                self.driver.execute_script("window.scrollTo(0, 50);")
                time.sleep(1)

            # Progressive loading strategy
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    print(f"Loading attempt {attempt + 1}/{max_attempts}")

                    # Step 1: Wait for basic page structure
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )

                    # Step 2: Wake up the page with interactions
                    try:
                        self.driver.execute_script("document.body.click();")
                        time.sleep(1)
                        self.driver.execute_script("window.scrollTo(0, 100);")
                        time.sleep(1)
                        self.driver.execute_script("window.scrollTo(0, 0);")
                    except:
                        pass

                    # Step 3: Check for Instagram content with flexible selectors
                    content_found = False
                    selectors_to_try = [
                        # Logged in indicators
                        ("svg[aria-label='Home']", "home_icon"),
                        ("svg[aria-label*='Home']", "home_variant"),

                        # Login form indicators
                        ("input[name='username']", "username_input"),
                        ("input[placeholder*='username']",
                         "username_placeholder"),
                        ("form[method='post']", "login_form"),
                        ("[data-testid='royal_login_form']", "royal_form")
                    ]

                    for selector, name in selectors_to_try:
                        try:
                            elements = self.driver.find_elements(
                                By.CSS_SELECTOR, selector)
                            if elements:
                                print(f"✅ Found {name} - Instagram loaded")
                                content_found = True

                                # Determine login status
                                if name.startswith("home"):
                                    self.logged_in = True
                                    self.logger.info("✅ Already logged in")
                                    return True
                                elif name.startswith("username") or name.endswith("form"):
                                    self.logged_in = False
                                    self.logger.info("ℹ️ Not logged in")
                                    return False
                                break
                        except:
                            continue

                    if content_found:
                        break

                    # If no content found, try revival
                    if attempt < max_attempts - 1:
                        print("🔄 No Instagram content found - attempting revival")
                        self.driver.execute_script("window.location.reload();")
                        time.sleep(3)

                except TimeoutException:
                    if attempt < max_attempts - 1:
                        print(
                            f"⚠️ Attempt {attempt + 1} timed out - trying revival")
                        try:
                            # Force interaction to wake up page
                            self.driver.execute_script(
                                "document.body.style.display='none';")
                            time.sleep(0.5)
                            self.driver.execute_script(
                                "document.body.style.display='';")
                            time.sleep(2)
                        except:
                            pass
                    else:
                        raise

            # Ultimate fallback
            # wait for 30 sec to see if it is possible to be handled by observer
            time(30)
            print("⚠️ Could not determine login status - assuming not logged in")
            self.logged_in = False
            return False

        except Exception as e:
            self.logger.error(f"Error checking login status: {e}")
            # Try one final health check
            try:
                self.driver.execute_script("return 'alive';")
                print("🔄 Driver still alive despite error")
            except:
                print("❌ Driver appears dead")

            self.logged_in = False
            return False

        finally:
            # Restore original timeout
            try:
                self.driver.set_page_load_timeout(original_timeout)
            except:
                pass

    def perform_login(self, username: str, password: str, secret_key: str):
        """Perform Instagram login and save cookies"""
        try:
            self.logger.info("Performing Instagram login...")

            # Perform login
            login_success = insta_login(
                driver=self.driver, username=username, password=password, secret_key=secret_key, observer=self.observer, webhook=self.webhook)

            if login_success:
                time.sleep(3)  # Wait for login to complete

                # Verify login was successful
                if self.check_login_status():
                    self.logged_in = True

                    # Save cookies after successful login
                    if self.save_cookies():
                        self.logger.info(
                            "✅ Login successful and cookies saved")
                        return True
                    else:
                        self.logger.warning(
                            "⚠️ Login successful but failed to save cookies")
                        return True  # Still return True as login worked
                else:
                    self.logger.error("❌ Login appears to have failed")
                    return False
            else:
                self.logger.error("❌ Login function returned failure")
                return False

        except RuntimeError:
            raise

        except Exception as e:
            self.logger.error(f"❌ Login process failed: {e}")
            return False

    def save_cookies(self):
        """Save current cookies to GoLogin profile"""
        try:
            if not self.driver or not self.gologin:
                return False

            # Get current cookies
            self.cookies = self.driver.get_cookies()
            self.logger.info(f"Attempting to save {len(self.cookies)} cookies")

            # Filter Instagram cookies
            insta_cookies = [
                cookie for cookie in self.cookies if 'instagram.com' in cookie.get('domain', '')]
            self.logger.info(
                f"Found {len(insta_cookies)} Instagram-specific cookies")

            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to save cookies: {e}")
            return False

    def run_activities(self):
        """Run Instagram activities"""
        try:
            if not self.logged_in:
                self.logger.error("Cannot run activities - not logged in")
                return False

            self.logger.info("Starting Instagram activities...")

            if (self.task_type == "LOGIN"):
                goto_profile_and_save_image(driver=self.driver,
                                            observer=self.observer,
                                            username=self.webhook.attributes.get(
                                                'username'),
                                            webhook=self.webhook)

            elif (self.task_type == "WARMUP"):
                # warmup_type = self.webhook.attributes.get("warmup_type", 1)

                browse_explore_page(self.driver, self.observer)
                # if (warmup_type == 1):
                #     # explore_reels_randomly(self.driver, self.observer, count=random.randint(1,3))
                # elif (warmup_type == 2):
                # else:
                #     print("Viewing stories")
                #     browse_explore_page(self.driver, self.observer)

                self.webhook.update_account_status("warmup_completed", {
                    "account_id": self.webhook.account_id,
                    "profile_id": self.profile_id,
                    "cookies": self.cookies
                })

                print("🏠 Returning to Instagram home page.")
                self.driver.get("https://www.instagram.com/")

            elif (self.task_type == "START_CAMPAIGNING"):
                retry_count = 1
                messages = self.webhook.attributes.get(
                    'messages_to_send', [])
                send_to_new_users_only = self.webhook.attributes.get(
                    'send_to_new_users_only', False)

                while (retry_count <= 3):
                    print(f"Attempting #{retry_count} to process {len(messages)} messages")
                    successful_fresh_dms, _ ,_ = search_and_message_users(
                        driver=self.driver,
                        messages_to_send=messages,
                        observer=self.observer,
                        webhook=self.webhook,
                        send_to_new_users_only= send_to_new_users_only
                    )

                    recived_dms_count = sum(1 for m in messages if m.get("type") == "MESSAGE")

                    # means some of the messages have failed
                    if (successful_fresh_dms >= recived_dms_count):
                        break

                    # send webhook and ask for some extra dms-----------
                    response = self.webhook.update_campaign_status("call_for_extra_dms",{
                        "campaign_id": self.webhook.attributes.get("campaign_id", None),
                        "qty": recived_dms_count - successful_fresh_dms
                    })

                    extra_data = response.get("data",[])
                    if not extra_data:
                        print("⚠️ No extra messages received, stopping retries")
                        break

                    messages = extra_data
                    time.sleep(20)
                    retry_count += 1
                    
            time.sleep(5)
            return True

        except RuntimeError as r:
            raise

        except Exception as e:
            self.logger.error(f"❌ Activities failed: {e}")

            # retry the task again, because it may have happended due to page not loading ------
            if (self.task_type != "LOGIN"):
                self.need_task_retry = True

            return False

    def execute(self):
        """Main execution method"""
        try:
            # Initialize session ----------
            if not self.initialize_session():
                return False

            time.sleep(2)

            # Check login -----------------
            if self.check_login_status():
                self.logger.info("Already logged in, skipping login process")

            else:
                if self.task_type == "LOGIN":
                    username = self.webhook.attributes.get('username')
                    password = self.webhook.attributes.get('password')
                    secret_key = self.webhook.attributes.get('secret_key')

                    if not username or not password or not secret_key:
                        raise Exception(
                            "Invalid Request, Attributes not found")

                    if not self.perform_login(username=username, password=password, secret_key=secret_key):
                        self.webhook.update_account_status("login_failed", {
                            "account_id": self.webhook.account_id,
                            "cookies": self.cookies,
                            "profile_id": self.profile_id
                        })
                        return True

                    self.webhook.update_account_status("login_completed", {
                        "account_id": self.webhook.account_id,
                        "profile_id": self.profile_id,
                        "cookies": self.cookies
                    })

                else:
                    print(
                        "Waiting for screen observer if it fixes the problem, and then will check again")

                    if not self.check_login_status():
                        self.webhook.update_account_status("login_required", {
                            "account_id": self.webhook.account_id,
                            "cookies": self.cookies
                        })
                        return True

            time.sleep(5)

            # Run activities
            if not self.run_activities():
                return False

            time.sleep(10)
            return True

        except RuntimeError as r:
            print(" ❌ Found Runtime Error >> ", str(r))
            return True

        except Exception as e:
            self.logger.error(f"❌ Execution failed: {e}")
            return False

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        try:
            self.logger.info("Cleaning up resources...")

            # Save cookies before cleanup
            if self.logged_in and self.driver and self.gologin:
                try:
                    self.save_cookies()
                except Exception as e:
                    self.logger.error(
                        f"Failed to save cookies during cleanup: {e}")

            # Stop observer
            if self.observer:
                try:
                    self.observer.stop_monitoring()
                    self.logger.info("✅ Observer stopped")
                except Exception as e:
                    self.logger.error(f"Error stopping observer: {e}")

            # Stop GoLogin session
            if self.gologin:
                try:
                    self.gologin.stop_gologin_session()
                    self.logger.info("✅ GoLogin session stopped")
                except Exception as e:
                    self.logger.error(f"Error stopping GoLogin session: {e}")

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
