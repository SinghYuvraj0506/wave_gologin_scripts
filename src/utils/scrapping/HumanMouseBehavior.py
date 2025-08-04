import random
import time
import math
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException, StaleElementReferenceException


class HumanMouseBehavior:
    """
    A class to simulate human-like mouse movements and interactions
    """
    
    def __init__(self, driver):
        self.driver = driver
        self.action_chains = ActionChains(driver)
        

    def bezier_curve(self, start_x, start_y, end_x, end_y, num_points=50):
        """
        Generate points along a bezier curve for smooth mouse movement
        """
        # Create control points for bezier curve
        ctrl1_x = start_x + random.randint(-100, 100)
        ctrl1_y = start_y + random.randint(-100, 100)
        ctrl2_x = end_x + random.randint(-100, 100)
        ctrl2_y = end_y + random.randint(-100, 100)
        
        points = []
        for i in range(num_points):
            t = i / (num_points - 1)
            
            # Bezier curve formula
            x = (1-t)**3 * start_x + 3*(1-t)**2*t * ctrl1_x + 3*(1-t)*t**2 * ctrl2_x + t**3 * end_x
            y = (1-t)**3 * start_y + 3*(1-t)**2*t * ctrl1_y + 3*(1-t)*t**2 * ctrl2_y + t**3 * end_y
            
            points.append((int(x), int(y)))
        
        return points
    

    def human_like_move_to_element(self, element, click=True, hover_duration=None, speed='normal'):
        """
        Move mouse to element with human-like behavior and optionally click
        
        Args:
            element: WebElement to move to
            click: Whether to click the element (default: True)
            hover_duration: Time to hover before clicking (random if None)
            speed: 'slow', 'normal', 'fast' - controls movement speed
        
        Returns:
            bool: Success status
        """
        
        try:
            # Wait for element to be present and visible
            wait = WebDriverWait(self.driver, 10)
            element = wait.until(EC.element_to_be_clickable(element))
            # Get element location and size
            element_rect = element.rect
            
            # Add some randomness to target position (don't always click center)
            offset_x = random.randint(-element_rect['width']//4, element_rect['width']//4)
            offset_y = random.randint(-element_rect['height']//4, element_rect['height']//4)
            
            # Speed configurations
            speed_configs = {
                'slow': {'points': 25, 'base_delay': 0.008, 'hover': (0.2, 0.6)},
                'normal': {'points': 15, 'base_delay': 0.003, 'hover': (0.05, 0.2)},
                'fast': {'points': 8, 'base_delay': 0.001, 'hover': (0.01, 0.05)}
            }
            
            config = speed_configs.get(speed, speed_configs['normal'])
            
            # Sometimes just move directly (30% chance for very natural behavior)
            if random.random() < 0.3:
                # Direct move with small offset
                self.action_chains.move_to_element_with_offset(element, offset_x, offset_y)
                self.action_chains.perform()
                self.action_chains = ActionChains(self.driver)

            else:
                # Get current approximate position
                viewport_center_x = self.driver.get_window_size()['width'] // 2
                viewport_center_y = self.driver.get_window_size()['height'] // 2
                
                # Calculate target position
                target_x = element_rect['x'] + element_rect['width'] // 2 + offset_x
                target_y = element_rect['y'] + element_rect['height'] // 2 + offset_y
                
                # Generate fewer points for faster movement
                path_points = self.bezier_curve(viewport_center_x, viewport_center_y, target_x, target_y, config['points'])
                
                # Move along path with optimized timing
                for i, (x, y) in enumerate(path_points[::2]):  # Skip every other point for speed
                    # Calculate offset from element center
                    element_center_x = element_rect['x'] + element_rect['width'] // 2
                    element_center_y = element_rect['y'] + element_rect['height'] // 2
                    
                    offset_x_calc = x - element_center_x
                    offset_y_calc = y - element_center_y

                    print(offset_x_calc, offset_y_calc)
                    
                    # Move to point
                    self.action_chains.move_to_element_with_offset(element, offset_x_calc, offset_y_calc)
                    self.action_chains.perform()
                    
                    # Optimized delay - much faster
                    delay = config['base_delay'] + random.uniform(0, 0.002)
                    time.sleep(delay)
                    
                    # Reset action chains
                    self.action_chains = ActionChains(self.driver)

            # Minimal hover time
            if hover_duration is None:
                hover_duration = random.uniform(*config['hover'])
            
            time.sleep(hover_duration)
            
            # Perform click if requested
            if click:
                # Reduced double-check probability
                if random.random() < 0.15:  # 15% chance instead of 30%
                    time.sleep(random.uniform(0.02, 0.08))
                
                # Minimal micro-adjustment
                micro_x = random.randint(-1, 1)
                micro_y = random.randint(-1, 1)
                self.action_chains.move_to_element_with_offset(element, micro_x, micro_y)
                self.action_chains.click()
                self.action_chains.perform()

                print("🐁 clicked via mouse")
                
                # Very brief pause after click
                time.sleep(random.uniform(0.01, 0.05))
            
            return True
            
        except (StaleElementReferenceException) as e:
            print(f"Stale error: {e}")
            return False
        except (TimeoutException, ElementNotInteractableException) as e:
            print(f"Element not found, Timeout Error: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False
    


    def random_mouse_jitter(self, duration=None, intensity='medium'):
        """
        Create random mouse movements (jittering) for specified duration
        
        Args:
            duration: Time to jitter in seconds (random if None)
            intensity: 'low', 'medium', or 'high' - controls movement range
        """
        if duration is None:
            duration = random.uniform(1, 3)
        
        # Set movement ranges based on intensity
        intensity_ranges = {
            'low': (-10, 10),
            'medium': (-30, 30),
            'high': (-80, 80)
        }
        
        move_range = intensity_ranges.get(intensity, intensity_ranges['medium'])
        
        start_time = time.time()
        
        # Get a reference element (body) to base movements on
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
        except:
            print("Could not find body element for jittering")
            return
        
        while time.time() - start_time < duration:
            # Random movement
            x_offset = random.randint(*move_range)
            y_offset = random.randint(*move_range)

            # Move relative to body element
            self.action_chains.move_to_element_with_offset(body, x_offset, y_offset)
            self.action_chains.perform()
            
            # Reset action chains
            self.action_chains = ActionChains(self.driver)
            
            # Random delay between movements
            delay = random.uniform(0.05, 0.2)
            time.sleep(delay)
    

    def natural_scroll(self, direction='down', amount=None):
        """
        Simulates human-like scrolling up and down on a webpage.

        Args:
            driver: Selenium WebDriver instance.
            scroll_count: Number of scroll steps to perform.
            scroll_distance: Distance in pixels for each scroll.
            scroll_pause: Average pause between scrolls in seconds.
        """
        
        if amount is None:
            amount = random.randint(200, 800)
        
        # Scroll in small increments for natural behavior
        scroll_steps = random.randint(5, 12)
        step_size = amount // scroll_steps
        
        for i in range (1,scroll_steps):
            if direction == 'down':
                self.driver.execute_script(f"window.scrollBy(0, {i*step_size})")
            else:
                self.driver.execute_script(f"window.scrollBy(0, {i*step_size})")
            
            # Small delay between scroll steps
            time.sleep(random.uniform(0.4, 0.9))
    

    def quick_move_to_element(self, element, click=True):
        """
        Fast, direct move to element - for when you need speed over stealth
        
        Args:
            element: WebElement to move to
            click: Whether to click the element
        
        Returns:
            bool: Success status
        """
        try:
            # Wait for element
            wait = WebDriverWait(self.driver, 5)
            element = wait.until(EC.element_to_be_clickable(element))
            
            # Small random offset to avoid clicking exact center
            offset_x = random.randint(-3, 3)
            offset_y = random.randint(-3, 3)
            
            # Direct move and click
            self.action_chains.move_to_element_with_offset(element, offset_x, offset_y)
            
            if click:
                self.action_chains.click()
            
            self.action_chains.perform()
            
            # Minimal delay
            time.sleep(random.uniform(0.01, 0.03))
            
            return True
            
        except Exception as e:
            print(f"Error in quick move: {e}")
            return False


    def focus_on_screen(self):
        try:
            # Click somewhere in the center of the screen to focus
            self.action_chains.move_by_offset(100, 100).click().perform()
            self.action_chains.move_by_offset(-100, -100).perform()  
            print("🖱️ Focused on screen.")
        except Exception as e:
            print("⚠️ Failed to focus screen:", e)