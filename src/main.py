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
    def __init__(self, proxy_country: str, proxy_city: str, session_id: str, task_type: str, webhook: WebhookUtils, profile_id: str = None):
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
                        ("a[href='/']", "home_link"), 
                        ("[data-testid='mobile-nav-home']", "mobile_home"),
                        ("svg[aria-label*='Home']", "home_variant"),
                        
                        # Login form indicators
                        ("input[name='username']", "username_input"),
                        ("input[placeholder*='username']", "username_placeholder"),
                        ("form[method='post']", "login_form"),
                        ("[data-testid='royal_login_form']", "royal_form")
                    ]
                    
                    for selector, name in selectors_to_try:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
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
                        print(f"⚠️ Attempt {attempt + 1} timed out - trying revival")
                        try:
                            # Force interaction to wake up page
                            self.driver.execute_script("document.body.style.display='none';")
                            time.sleep(0.5)
                            self.driver.execute_script("document.body.style.display='';")
                            time.sleep(2)
                        except:
                            pass
                    else:
                        raise
            
            # Final fallback - check current URL and make educated guess
            current_url = self.driver.current_url
            if "instagram.com" in current_url:
                if "/accounts/login" in current_url or current_url.count("/") <= 3:
                    print("📍 URL suggests login page")
                    self.logged_in = False
                    return False
                else:
                    print("📍 URL suggests logged in state")
                    self.logged_in = True
                    return True
            
            # Ultimate fallback
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
                warmup_type = self.webhook.attributes.get("warmup_type", 1)

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
                    messages_to_send=self.webhook.attributes.get(
                        'messages_to_send', []),
                    observer=self.observer,
                    webhook=self.webhook
                )
                
                # schedule next bactch of dm processing
                if self.webhook.attributes.get("next_process_in") is not None:
                    self.webhook.update_campaign_status("schedule_next_iteration",{
                        "campaign_id": self.webhook.attributes.get("campaign_id"),
                        "delay_in_minutes": self.webhook.attributes.get("next_process_in")
                    })

            elif (self.task_type != "LOGIN"):
                raise Exception("Invalid Task Type")

            time.sleep(5)
            return True
        
        except RuntimeError as r:
            raise

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
                    username = self.webhook.attributes.get('username')
                    password = self.webhook.attributes.get('password')
                    secret_key = self.webhook.attributes.get('secret_key')

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
                    #  login required would trigger and ask to login again nd if login is genuiinloy faulted then it would say login failed
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
