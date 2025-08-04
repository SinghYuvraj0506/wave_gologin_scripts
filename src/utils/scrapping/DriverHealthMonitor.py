import time
import random
from selenium.common.exceptions import TimeoutException, WebDriverException

class DriverHealthMonitor:
    def __init__(self, driver):
        self.driver = driver
        self.last_health_check = time.time()
        self.health_check_interval = 15
        self.connection_timeout_count = 0  # Track consecutive timeouts
        
    def revive_driver(self, method="scroll"):
        """Revive unresponsive driver using various methods"""
        try:
            if method == "scroll":
                # Use shorter timeout for scroll operations
                self.driver.set_page_load_timeout(30)  # Reduce from default 120s
                scroll_amount = random.randint(50, 200)
                self.driver.execute_script(f"window.scrollTo(0, {scroll_amount});")
                time.sleep(0.5)
                self.driver.execute_script("window.scrollTo(0, 0);")
                
            elif method == "screenshot":
                # Quick screenshot with timeout handling
                try:
                    self.driver.get_screenshot_as_png()
                except Exception as e:
                    if "Read timed out" in str(e):
                        print("⚠️ Screenshot timeout, trying alternative revival")
                        return self.revive_driver("click_body")
                
            elif method == "refresh":
                current_url = self.driver.current_url
                self.driver.set_page_load_timeout(45)  # Shorter refresh timeout
                self.driver.refresh()
                time.sleep(3)
                
            elif method == "click_body":
                # Safest method - just execute JS
                self.driver.execute_script("document.body.click();")
                
            elif method == "minimal":  # NEW - minimal revival
                # Just check if driver is alive without heavy operations
                self.driver.execute_script("return 'alive';")
                
            print(f"✅ Driver revived using: {method}")
            self.last_health_check = time.time()
            self.connection_timeout_count = 0  # Reset counter on success
            return True
            
        except Exception as e:
            if "Read timed out" in str(e) or "HTTPConnectionPool" in str(e):
                self.connection_timeout_count += 1
                print(f"⚠️ Connection timeout #{self.connection_timeout_count} with {method}: {e}")
                
                # If multiple timeouts, try minimal approach
                if self.connection_timeout_count >= 2 and method != "minimal":
                    return self.revive_driver("minimal")
                    
            print(f"❌ Driver revive failed with {method}: {e}")
            return False
    
    def check_driver_health(self):
        """Lightweight health check"""
        try:
            # Minimal responsiveness test
            result = self.driver.execute_script("return document.readyState;")
            self.last_health_check = time.time()
            return True
        except Exception as e:
            if "Read timed out" in str(e):
                self.connection_timeout_count += 1
            return False
    
    def auto_revive_if_needed(self):
        """Auto-revive with timeout awareness"""
        current_time = time.time()
        
        if current_time - self.last_health_check > self.health_check_interval:
            if not self.check_driver_health():
                print("🔄 Driver appears stuck, attempting revival...")
                
                # Use progressive revival strategy based on timeout count
                if self.connection_timeout_count == 0:
                    methods = ["click_body", "scroll", "screenshot"]
                elif self.connection_timeout_count == 1:
                    methods = ["minimal", "click_body"]
                else:
                    methods = ["minimal"]  # Only minimal operations if many timeouts
                    
                for method in methods:
                    if self.revive_driver(method):
                        break
                    time.sleep(2)  # Longer delay between attempts when timing out