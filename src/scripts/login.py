from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior
from utils.scrapping.HumanTypingBehavior import HumanTypingBehavior
from config import Config
from scripts.twofactorCheck import handle_two_factor_authentication
import time

def insta_login(driver):
    """
    Logs into Instagram using the provided Selenium driver.

    Args:
        driver: An instance of a Selenium WebDriver.

    Returns:
        bool: True if login is successful, False otherwise.
    """

    try:
        human_mouse = HumanMouseBehavior(driver)
        human_typing = HumanTypingBehavior(driver)

        driver.get("https://www.instagram.com")
        wait = WebDriverWait(driver, 15)

        human_mouse.random_mouse_jitter(4)

        username = Config.INSTA_USERNAME
        password = Config.INSTA_PASSWORD

        username_input = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        password_input = wait.until(EC.presence_of_element_located((By.NAME, "password")))

        human_mouse.human_like_move_to_element(element=username_input, click=True)
        human_typing.human_like_type(element=username_input,text=username, typing_speed="normal")

        time.sleep(2)

        human_mouse.human_like_move_to_element(element=password_input, click=True)
        human_typing.human_like_type(element=password_input,text=password, typing_speed="slow")

        time.sleep(3)
        
        password_input.send_keys(Keys.RETURN)

        time.sleep(4)

        # Handle 2FA if required
        if not handle_two_factor_authentication(driver):
            return False

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/{}/']".format(username))))
        print("✅ Login successful!")
        return True

    except TimeoutException as e:
        print(f"❌ Error during login: A timeout occurred. The page might be slow to load or an element was not found in time.")
        print(f"Details: {e}")
        return False
    except NoSuchElementException as e:
        print(f"❌ Error during login: Could not find a required element on the page.")
        print(f"Details: {e}")
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred during login: {e}")
        return False


