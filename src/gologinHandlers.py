from utils.scrapping.BandwidthManager import BandwidthManager
from gologin import GoLogin
from typing import Optional, Dict, Any
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from config import Config
from utils.basicHelpers import get_proxy_config
import traceback
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import time
from utils.exceptions import GologinConnectionError, GologinError, GologinProfileNotFoundError


class GologinHandler:
    def __init__(self, proxy_country: str, proxy_city: str, proxy_city_fallbacks: list[str], session_id: str, account_id: str, profile_id: str = None, task_type: str = None):
        token = Config.GL_API_TOKEN
        if not token:
            raise GologinError("Gologin Token not found")

        params = {
            'token': token,
            'extra_params': [
                # CORE
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080",
                "--disable-gpu",                          # ← comma fixed

                # VULKAN FIXES
                "--disable-vulkan",                       # ← comma fixed
                "--disable-vulkan-surface",
                "--disable-vulkan-fallback-to-gl-for-testing",
                "--use-vulkan=disabled",
                "--disable-features=Vulkan",

                # FORCE SOFTWARE RENDERING
                "--use-gl=disabled",                      # ← comma fixed
                "--disable-accelerated-2d-canvas",
                "--disable-accelerated-video-decode",
                "--disable-software-rasterizer",
                "--disable-gpu-rasterization",
                "--disable-gpu-memory-buffer-video-frames",

                # DISABLE WEBGL & 3D
                "--disable-features=VizDisplayCompositor,Vulkan,UseSkiaRenderer,WebGL,WebGL2",  # ← comma fixed
                "--disable-3d-apis",
                "--disable-webgl",
                "--disable-webgl2",

                # BACKGROUND THROTTLING
                "--disable-background-timer-throttling",  # ← comma fixed
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",

                # CONNECTION STABILITY
                "--max_old_space_size=2048",              # ← comma fixed
                "--disable-extensions-http-throttling",

                # ✅ NEW: BLOCK GOOGLE UPDATE/TELEMETRY (saves proxy bandwidth)
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-sync",
                "--no-first-run",
                "--disable-default-apps",
                "--disable-domain-reliability",
                "--disable-breakpad",
                "--no-pings",
                "--disable-client-side-phishing-detection",
                "--disable-hang-monitor",
            ]
        }

        self.gologin = GoLogin(params)
        self.profile_id = profile_id
        self.account_id = account_id
        self.driver = None
        self.proxyConfig = None

        if profile_id is None:
            self.create_gologin_profile()

        # check for gologin retry
        try:
            self.gologin.setProfileId(self.profile_id)
        except Exception as e:
            if self.task_type != "LOGIN" :
                raise GologinProfileNotFoundError(f"Gologin profile not found for {self.account_id}")

            self.create_gologin_profile()
            self.gologin.setProfileId(self.profile_id)

        try:
            proxyConfig = get_proxy_config(
                session=session_id, city=proxy_city, country=proxy_country, fallbacks=proxy_city_fallbacks)
            self.proxyConfig = proxyConfig
            self.change_gologin_proxy(proxyConfig)
        except Exception as e:
            raise GologinError(
                f"Failed to set proxy for {proxy_country}, tried main '{proxy_city}' and fallbacks {proxy_city_fallbacks}, error - {e}"
            )
        

    def connect_gologin_session(self, bandwidthManager: BandwidthManager):
        try:
            print('📡 Starting GoLogin session...')
            debugger_address = self.gologin.start()

            # Dynamically fetch the correct ChromeDriver for GoLogin's Chromium version
            # chromium_version = self.gologin.get_chromium_version()
            # print(f'🔧 GoLogin Chromium version: {chromium_version}')
            
            # service = Service(
            #     ChromeDriverManager(driver_version=chromium_version).install()
            # )
            service = Service("/usr/local/bin/chromedriver")

            chrome_options = webdriver.ChromeOptions()

            prefs = {
                "profile.credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "profile.password_manager_leak_detection": False
            }


            chrome_options.add_experimental_option("prefs", prefs)
            chrome_options.add_experimental_option(
                "debuggerAddress", debugger_address)

            print('🌐 Connecting to browser...')
            self.driver = webdriver.Chrome(
                service=service, options=chrome_options)
            
            bandwidthManager.enable(self.driver)
            time.sleep(3)
            print("✅ GoLogin session connected and ready")

        except Exception as e:
            traceback.print_exc()
            raise GologinConnectionError(f"Gologin Connection Error: {str(e)}")


    def stop_gologin_session(self):
        try:
            if hasattr(self.gologin, "stop"):
                self.gologin.stop()
                print('✅ GoLogin session stopped successfully')
        except Exception as e:
            raise GologinError(f"GologinStop Error: {str(e)}")


    def create_gologin_profile(self):
        try:
            self.profile_id = self.gologin.createProfileWithCustomParams({
                "os": "lin",
                "name": f"instagram-bot-{self.account_id}",
                "autoLang": False,
                "navigator": {
                    "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.7049.41 Safari/537.36",
                    "resolution": "1920x1080",
                    "language": "en-US",
                    "platform": "Linux x86_64"
                },
                "webRTC": {
                    "enable": True,
                    "isEmptyIceList": False,
                    "mode": "alerted"
                },
                "webGL": {
                    "mode": "noise",
                    "getClientRectsNoise": 1,
                    "noise": 1
                },
                "timezone": {
                    "enabled": True,
                    "fillBasedOnIp": True,
                },
                "geolocation": {
                    "mode": "allow",
                    "enabled": True,
                    "fillBasedOnIp": True
                }
            })

            print('✅ GoLogin profile created successfully', self.profile_id)

        except Exception as e:
            print(e)
            raise GologinError(f"GologinProfileCreation Error: {str(e)}")


    def change_gologin_proxy(self, proxyConfig):
        self.gologin.changeProfileProxy(self.profile_id, proxyConfig)
        print('✅ GoLogin proxy Alloted successfully')


    def download_cookies(self):
        cookies = self.gologin.downloadCookies()
        self.gologin.writeCookiesFromServer()
        print("cookies", cookies)
