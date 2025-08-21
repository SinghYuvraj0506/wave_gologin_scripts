import time
import threading
import logging
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
from datetime import datetime
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.DriverHealthMonitor import DriverHealthMonitor


class ScreenObserver:
    """
    A comprehensive observer that monitors URL changes and dialog appearances
    with automatic handling capabilities for Instagram
    """

    def __init__(self, driver, callback_function=None, log_level=logging.INFO):
        self.driver = driver
        self.callback_function = callback_function
        self.current_url = ""
        self.is_monitoring = False
        self.monitor_thread = None
        self.check_interval = 10
        self.human_mouse = HumanMouseBehavior(driver)
        self.health_monitor = DriverHealthMonitor(driver)

        # Setup logging
        logging.basicConfig(
            level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

        # Dialog detection patterns
        self.dialog_patterns = {
            'cookies_consent': [
                "//button[contains(text(), 'Accept')]",
                "//button[contains(text(), 'Allow')]",
                "//div[contains(text(), 'cookies')]//button",
                "//button[contains(text(), 'Accept All')]"
            ],
            'notification_popup': [
                "//div[contains(text(), 'notifications')]",
                "//button[contains(text(), 'Not Now')]",
            ],
            'rate_limit': [
                "//div[contains(text(), 'Try again later')]",
                "//div[contains(text(), 'Please wait')]",
                "//div[contains(text(), 'temporary')]",
                "//div[contains(text(), 'blocked')]"
            ],
            'captcha': [
                "//div[contains(text(), 'security check')]",
                "//div[contains(text(), 'verification')]",
                "//iframe[contains(@src, 'recaptcha')]",
                "//div[@class='g-recaptcha']"
            ],
            'suspicious_activity': [
                "//div[contains(text(), 'suspicious activity')]",
                "//div[contains(text(), 'unusual activity')]",
                "//button[contains(text(), 'This Was Me')]"
            ],
            'account_suspended': [
                "//div[contains(text(), 'account has been')]",
                "//div[contains(text(), 'suspended')]",
                "//div[contains(text(), 'disabled')]"
            ]
        }

        # Action handlers for different dialog types
        self.action_handlers = {
            'cookies_consent': self.handle_cookies_consent,
            'notification_popup': self.handle_notification_popup,
            'rate_limit': self.handle_rate_limit,
            'captcha': self.handle_captcha,
            'suspicious_activity': self.handle_suspicious_activity,
            'account_suspended': self.handle_account_suspended
        }

        # URL change handlers
        self.url_change_handlers = {
            'blocked_page': self.handle_blocked_page,
            'onetap_save_info': self.handle_onetap_save_info,
            'challenge_redirect': self.handle_challenge_redirect,
            'consent': self.handle_consent_redirect
        }

        # Initialize current URL
        try:
            self.current_url = self.driver.current_url
        except:
            self.current_url = ""

    def start_monitoring(self):
        """Start the monitoring thread"""
        if not self.is_monitoring:
            self.is_monitoring = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            self.logger.info("Screen monitoring started")

    def stop_monitoring(self):
        """Stop the monitoring thread"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        self.logger.info("Screen monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                # Auto-revive check
                self.health_monitor.auto_revive_if_needed()

                # Check for URL changes
                self._check_url_changes()

                # Check for dialogs
                self._check_dialogs()

                # Sleep before next check
                time.sleep(self.check_interval)

            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                self.health_monitor.revive_driver("scroll")
                time.sleep(1)  # Wait longer on error

    def _check_url_changes(self):
        """Check for URL changes and handle them"""
        try:
            new_url = self.driver.current_url

            if new_url != self.current_url:
                self.logger.info(
                    f"URL changed: {self.current_url} -> {new_url}")

                # Handle specific URL patterns
                self._handle_url_change(self.current_url, new_url)

                # Update current URL
                self.current_url = new_url

                # Call callback if provided
                if self.callback_function:
                    self.callback_function('url_change', {
                        'old_url': self.current_url,
                        'new_url': new_url,
                        'timestamp': datetime.now().isoformat()
                    })

        except Exception as e:
            self.logger.error(f"Error checking URL changes: {e}")

    def _check_dialogs(self):
        """Check for dialogs and handle them"""
        try:
            # Check Instagram-specific dialogs first
            for dialog_type, patterns in self.dialog_patterns.items():
                if self._detect_dialog(patterns):

                    self.callback_function("dialog_detected",{
                        "type":dialog_type,
                        'timestamp': datetime.now().isoformat(),
                        'url': self.current_url
                    })

                    success = self._handle_dialog(dialog_type)

                    if not success:
                        self.logger.warning(
                            f"Failed to handle dialog: {dialog_type}")
                        self._request_manual_intervention(f'Found dialog error - {dialog_type}')

                    return  # Handle one dialog at a time

        except Exception as e:
            self.logger.error(f"Error checking dialogs: {e}")

    def _detect_dialog(self, patterns):
        """Detect if any dialog pattern is present"""
        for pattern in patterns:
            try:
                element = self.driver.find_element(By.XPATH, pattern)
                if element.is_displayed():
                    return True
            except (NoSuchElementException, TimeoutException):
                continue
        return False

    def _handle_dialog(self, dialog_type):
        """Handle detected dialog using appropriate handler"""
        if dialog_type in self.action_handlers:
            try:
                # Revive after dialog interaction
                self.health_monitor.revive_driver("click_body")
                return self.action_handlers[dialog_type]()
            except Exception as e:
                self.logger.error(f"Error handling dialog {dialog_type}: {e}")
                return False
        return False

    def _handle_url_change(self, old_url, new_url):
        """Handle URL changes with specific patterns"""
        # Check for onetap save info page
        self.health_monitor.revive_driver("scroll")

        if 'accounts/onetap' in new_url:
            self.url_change_handlers['onetap_save_info'](old_url, new_url)

        elif '/consent' in new_url:
            self.url_change_handlers['consent'](
                old_url, new_url)

        # Check for challenge redirect (excluding two-factor)
        elif '/challenge' in new_url and 'two_factor' not in new_url:
            self.url_change_handlers['challenge_redirect'](old_url, new_url)

        # Check for blocked/suspended pages
        elif 'blocked' in new_url or 'suspended' in new_url:
            self.url_change_handlers['blocked_page'](old_url, new_url)

    def _request_manual_intervention(self, error=None, patterns={}):
        """Request manual intervention """

        if self.callback_function:
            self.callback_function('action_required', {
                'error': error if error is not None else "Unknown",
                'patterns': patterns,
                'url': self.driver.current_url,
                'timestamp': datetime.now().isoformat()
            })

    # Dialog Handler Methods -------------
    def handle_cookies_consent(self):
        """Handle cookies consent dialogs"""
        try:
            accept_selectors = [
                "//button[contains(text(), 'Accept')]",
                "//button[contains(text(), 'Allow')]",
                "//button[contains(text(), 'Accept All')]",
                "//button[contains(text(), 'OK')]"
            ]

            for selector in accept_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    if element.is_displayed():
                        element.click()
                        time.sleep(1)
                        return True
                except:
                    continue

            return False

        except Exception as e:
            self.logger.error(f"Error handling cookies consent: {e}")
            return False

    def handle_notification_popup(self):
        """Handle notification popups"""
        try:
            dismiss_selectors = [
                "//button[contains(text(), 'Not Now')]",
                "//button[contains(text(), 'Maybe Later')]",
                "//button[contains(text(), 'Cancel')]",
                "//button[@aria-label='Close']",
                "//button[contains(text(), 'No Thanks')]"
            ]

            for selector in dismiss_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    if element.is_displayed():
                        element.click()
                        time.sleep(1)
                        return True
                except:
                    continue

            return False

        except Exception as e:
            self.logger.error(f"Error handling notification popup: {e}")
            return False

    def handle_rate_limit(self):
        """Handle rate limit dialogs"""
        try:
            self.logger.warning("Rate limit detected - waiting and retrying")
            time.sleep(60)  # Wait 1 minute

            # Try to refresh the page
            self.driver.refresh()
            time.sleep(3)

            return True

        except Exception as e:
            self.logger.error(f"Error handling rate limit: {e}")
            return False

    def handle_captcha(self):
        """Handle CAPTCHA dialogs"""
        try:
            self.logger.warning(
                "CAPTCHA detected - requires manual intervention")
            return False

        except Exception as e:
            self.logger.error(f"Error handling CAPTCHA: {e}")
            return False

    def handle_suspicious_activity(self):
        """Handle suspicious activity dialogs"""
        try:
            # Try to click "This Was Me" button
            confirm_selectors = [
                "//button[contains(text(), 'This Was Me')]",
                "//button[contains(text(), 'Continue')]",
                "//button[contains(text(), 'Confirm')]"
            ]

            for selector in confirm_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    if element.is_displayed():
                        element.click()
                        time.sleep(2)
                        return True
                except:
                    continue

            return False

        except Exception as e:
            self.logger.error(f"Error handling suspicious activity: {e}")
            return False

    def handle_account_suspended(self):
        """Handle account suspended dialogs"""
        try:
            self.logger.error(
                "Account suspended - requires manual intervention")
            return False

        except Exception as e:
            self.logger.error(f"Error handling account suspended: {e}")
            return False


    # URL Change Handlers ------------------------------------
    def handle_onetap_save_info(self, old_url, new_url):
        """Handle onetap save info page redirect"""
        self.logger.info(
            f"Onetap save info page detected: {old_url} -> {new_url}")
        try:
            button_selector = "//main[@role='main']//button[@type='button']"

            element = self.driver.find_element(By.XPATH, button_selector)

            self.human_mouse.human_like_move_to_element(element, click=True)
            time.sleep(2)
            self.logger.info("Successfully clicked save info button at onetap")

        except Exception as e:
            self.logger.error(f"Error handling save info onetap: {e}")

            if self.callback_function:
                self._request_manual_intervention("Closing Save Info Dialog Failed")
                
    def handle_consent_redirect(self, old_url, new_url):
        """Handle onetap save info page redirect"""
        self.logger.info(
            f"Consent page detected: {old_url} -> {new_url}")
        
        response = False
        
        if "ad_free_subscription" in new_url:
            response = self.handle_consent_ad_free_subscription()

        if "user_cookie_choice_v2" in new_url:
            response = self.handle_consent_user_cookie_choice()

        if not response:
            if self.callback_function:
                self._request_manual_intervention("Closing Consent Failed")

    def handle_challenge_redirect(self, old_url, new_url):
        """Handle challenge redirect (excluding two-factor)"""
        self.logger.warning(
            f"Challenge redirect detected: {old_url} -> {new_url}")

        # Call callback to notify about challenge
        if self.callback_function:
            self._request_manual_intervention("Challenge detected")

    def handle_blocked_page(self, old_url, new_url):
        """Handle blocked page"""
        self.logger.warning(
            f"Blocked detected: {old_url} -> {new_url}")
        
        if self.callback_function:
            self._request_manual_intervention("Instagram detected ")

    def handle_consent_ad_free_subscription(self):
        try:
            time.sleep(2)
            # Fix XPath for Get Started button
            button_selector = "//div[@role='button']"
            element = self.driver.find_element(By.XPATH, button_selector)

            self.human_mouse.human_like_move_to_element(element, click=True)
            time.sleep(2)
            self.logger.info("Successfully clicked Get Started button")

        except Exception as e:
            self.logger.error(
                f"Error handling ad free subscription consent: {e}")
            return False

        time.sleep(2)

        try:
            # Check if dialog appears
            dialogElement = self.driver.find_element(
                By.XPATH, "//div[@role='dialog']")

            # Fix XPath for radio input
            inputToClick = self.driver.find_element(
                By.XPATH, "//input[@type='radio' and @value='PA']")
            self.human_mouse.human_like_move_to_element(
                inputToClick, click=True)
            time.sleep(2)

            # Fix XPath for Continue button
            continueButton = self.driver.find_element(
                By.XPATH, "//span[contains(text(),'Continue')]")
            self.human_mouse.human_like_move_to_element(
                continueButton, click=True)
            time.sleep(3)

            self.logger.info("Successfully clicked Continue Button")

        except Exception as e:
            self.logger.error(
                f"Error handling ad free subscription consent: {e}")
            return False
        


    def handle_consent_user_cookie_choice(self):
        try:
            time.sleep(2)
            # Fix XPath for Get Started button
            button_selector = "//div[@role='button' and contains(text(),'Allow all cookies')]"
            element = self.driver.find_element(By.XPATH, button_selector)

            self.human_mouse.human_like_move_to_element(element, click=True)
            time.sleep(2)
            self.logger.info("Successfully clicked Allow all cookies button")

        except Exception as e:
            self.logger.error(
                f"Error handling user cookie choice consent: {e}")
            return False