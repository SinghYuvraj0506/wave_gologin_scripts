from utils.scrapping.ScreenObserver import ScreenObserver, callbackEventHandler
import time
from scripts.login import insta_login
from scripts.exploreReel import explore_reels_randomly
from scripts.browseExplore import browse_explore_page
from scripts.goToMessages import search_and_message_users
from utils.basicHelpers import get_ip_proxy
import logging
from selenium.webdriver.common.by import By
from gologinHandlers import GologinHandler
from utils.WebhookUtils import WebhookUtils
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class MainExecutor:
    def __init__(self, proxy_country: str, proxy_city: str, session_id: str, task_type: str, webhook: WebhookUtils, extra_attributes: dict, profile_id: str = None):
        self.profile_id = profile_id
        self.proxy_country = proxy_country
        self.proxy_city = proxy_city
        self.session_id = session_id
        self.task_type = task_type
        self.logged_in = False
        self.gologin = None
        self.observer = None
        self.initialized = False
        self.cookies = None
        self.webhook = webhook
        self.extra_attributes = extra_attributes

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

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
                session_id=self.session_id,
                account_id=self.webhook.account_id
            )

            self.profile_id = self.gologin.profile_id

            self.gologin.connect_gologin_session()

            # Get driver from gologin handler
            self.driver = self.gologin.driver

            # Verify proxy
            get_ip_proxy(self.driver)

            # Start screen observer
            self.observer = ScreenObserver(
                self.driver, callback_function=callbackEventHandler)
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

            self.driver.get("https://www.instagram.com/")
            
            # Give time for heavy JS before interacting
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Try clicking body to wake the DOM
            try:
                self.driver.find_element(By.TAG_NAME, "body").click()
            except:
                pass

            # Explicitly wait for either home icon OR login form
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "svg[aria-label='Home']")),
                        EC.presence_of_element_located((By.NAME, "username"))
                    )
                )
            except TimeoutException:
                self.logger.warning("Page load slow — retrying once")
                self.driver.refresh()
                WebDriverWait(self.driver, 15).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "svg[aria-label='Home']")),
                        EC.presence_of_element_located((By.NAME, "username"))
                    )
                )

            # Decide status
            if self.driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Home']"):
                self.logged_in = True
                self.logger.info("✅ Already logged in")
                return True

            self.logged_in = False
            self.logger.info("ℹ️ Not logged in")
            return False

        except Exception as e:
            self.logger.error(f"Error checking login status: {e}")
            self.logged_in = False
            return False

    def perform_login(self, username: str, password: str, secret_key: str):
        """Perform Instagram login and save cookies"""
        try:
            self.logger.info("Performing Instagram login...")

            # Perform login
            login_success = insta_login(
                driver=self.driver, username=username, password=password, secret_key=secret_key)

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

            if (self.task_type == "WARMUP"):
                warmup_type = self.extra_attributes.get("warmup_type", 1)

                if (warmup_type == 1):
                    explore_reels_randomly(self.driver, self.observer)
                elif (warmup_type == 2):
                    browse_explore_page(self.driver, self.observer)
                else:
                    print("Viewing stories")
                    browse_explore_page(self.driver, self.observer)

                self.webhook.update_account_status("warmup_completed", {
                    "account_id": self.webhook.account_id,
                    "profile_id": self.profile_id,
                    "cookies": self.cookies
                })

            elif (self.task_type == "START_CAMPAIGNING"):
                search_and_message_users(
                    driver=self.driver,
                    messages_to_send=self.extra_attributes.get(
                        'messages_to_send', []),
                    observer=self.observer,
                    webhook=self.webhook
                )

            elif (self.task_type != "LOGIN"):
                raise Exception("Invalid Task Type")

            time.sleep(5)
            return True

        except Exception as e:
            self.logger.error(f"❌ Activities failed: {e}")
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
                    username = self.extra_attributes.get('username')
                    password = self.extra_attributes.get('password')
                    secret_key = self.extra_attributes.get('secret_key')

                    if not username or not password or not secret_key:
                        raise Exception(
                            "Invalid Request, Attributes not found")

                    if not self.perform_login(username=username, password=password, secret_key=secret_key):
                        self.webhook.update_account_status("login_failed", {
                            "account_id": self.webhook.account_id,
                            "cookies": self.cookies
                        })
                        return False

                    self.webhook.update_account_status("login_completed", {
                        "account_id": self.webhook.account_id,
                        "profile_id": self.profile_id,
                        "cookies": self.cookies
                    })

                else:
                    self.webhook.update_account_status("login_required", {
                        "account_id": self.webhook.account_id,
                        "cookies": self.cookies
                    })

            time.sleep(5)

            # Run activities
            if not self.run_activities():
                return False

            time.sleep(10)
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
