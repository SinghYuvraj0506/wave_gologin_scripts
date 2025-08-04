import random
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.scrapping.HumanMouseBehavior import HumanMouseBehavior

class BasicUtils:
    """
    A class to get all the scrapping instagram basic utils
    """
    
    def __init__(self, driver):
        self.driver = driver
        self.human_mouse = HumanMouseBehavior(driver)

    
    def click_anchor_by_href(self, href, timeout=10):
        """
        Find and click an anchor tag with the specified href
        
        Args:
            href: The href attribute value to search for
            timeout: Maximum time to wait for element (seconds)
        """

        # More robust XPath - handles both partial and exact matches
        xpath = f"//a[@href='{href}']"
        
        # Wait for the element to be present and clickable
        wait = WebDriverWait(self.driver, timeout)
        anchor_element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))

        # Add a small delay
        time.sleep(random.uniform(0.1, 0.5))
        
        # Use human-like mouse movement
        self.human_mouse.human_like_move_to_element(anchor_element, click=True)
        
        print(f"Successfully clicked anchor with href: {href}")
        return True

