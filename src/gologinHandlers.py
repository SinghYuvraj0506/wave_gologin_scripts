from gologin import GoLogin
from typing import Optional, Dict, Any
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from config import Config
from utils.basicHelpers import build_brightdata_proxy
import traceback
import time

class BaseGologinError(Exception):
    """Base exception for gologin related error"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class GologinHandler:
    def __init__(self, proxy_country:str, proxy_city:str, session_id:str, profile_id: str = None):
        token = Config.GL_API_TOKEN
        if not token:
            raise BaseGologinError("Gologin Token not found")

        params = {
            'token': token,
            'extra_params': [
                # '--headless=new',
                # '--no-sandbox',
                # '--disable-dev-shm-usage',
                # '--disable-gpu',
                # '--disable-gpu-sandbox',

                # VULKAN-SPECIFIC FIXES
                '--disable-vulkan',
                '--disable-vulkan-surface',
                '--disable-vulkan-fallback-to-gl-for-testing',
                '--use-vulkan=disabled',
                '--disable-features=Vulkan'

                # FORCE SOFTWARE RENDERING
                '--use-gl=disabled',
                '--disable-accelerated-2d-canvas',
                '--disable-accelerated-video-decode',
                '--disable-software-rasterizer',
                '--disable-gpu-rasterization',
                '--disable-gpu-memory-buffer-video-frames',

                # DISABLE PROBLEMATIC FEATURES
                '--disable-features=VizDisplayCompositor,Vulkan,UseSkiaRenderer,WebGL,WebGL2',
                '--disable-3d-apis',
                '--disable-webgl',
                '--disable-webgl2',

                # YOUR EXISTING FLAGS
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-blink-features=AutomationControlled',
                '--window-size=1920,1080'

                # CONNECTION STABILITY
                '--max_old_space_size=2048',
                '--disable-extensions-http-throttling'
            ]
        }

        self.gologin = GoLogin(params)
        self.profile_id = profile_id
        self.driver = None

        if profile_id is None:
            self.create_gologin_profile()

        self.gologin.setProfileId(self.profile_id)
        proxyConfig = build_brightdata_proxy(session=session_id, city=proxy_city, country=proxy_country)
        self.change_gologin_proxy(proxyConfig)


    def connect_gologin_session(self):
        try:
            print('📡 Starting GoLogin session...')
            debugger_address = self.gologin.start()
            # service = Service(ChromeDriverManager(
            #     driver_version=self.gologin.get_chromium_version()).install())
            service = Service("/usr/local/bin/chromedriver-137")

            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option(
                "debuggerAddress", debugger_address)

            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--disable-3d-apis")
            chrome_options.add_argument("--use-gl=swiftshader")
            chrome_options.add_argument("--disable-features=Vulkan")

            print('🌐 Connecting to browser...')
            self.driver = webdriver.Chrome(
                service=service, options=chrome_options)

        except Exception as e:
            traceback.print_exc()
            raise BaseGologinError("Gologin Connection Error", e)
        

    def stop_gologin_session(self):
        try:
            self.gologin.stop()
            print('✅ GoLogin session stopped successfully')
        except Exception as e:
            raise BaseGologinError("GologinStop Connection Error", e)


    def create_gologin_profile(self):
        try:
            self.profile_id = self.gologin.createProfileWithCustomParams({
                "os": "lin",
                "name": f"instagram-bot-{int(time.time())}",
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
            raise BaseGologinError("GologinProfileCreation Error", e)
        

    def change_gologin_proxy(self, proxyConfig):
        try:
            self.gologin.changeProfileProxy(self.profile_id, proxyConfig)
            print('✅ GoLogin proxy Alloted successfully')
        except Exception as e:
            raise BaseGologinError("GologinProxyAllot Error", e)

    def download_cookies(self):
        cookies = self.gologin.downloadCookies()
        self.gologin.writeCookiesFromServer()
        print("cookies", cookies)
