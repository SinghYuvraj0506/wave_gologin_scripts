import time
import pyotp
from config import Config
import json
from selenium.webdriver.common.by import By
import hmac
import hashlib
import requests

def build_proxyconfig(session:str, country:str, city:str) -> dict:
    if(Config.PROXY_PROVIDER == "SOAX"):
        city = city.lower().rstrip()
        user = f"{Config.SOAX_USER_NAME}-country-{country}-city-{city}-sessionid-{session}-sessionlength-3600-opt-wb"

        return {
            "mode": "http",
            "host": Config.SOAX_HOST,
            "port": int(Config.SOAX_PORT),
            "username": user,
            "password": Config.SOAX_PASSWORD
        }
    
    elif (Config.PROXY_PROVIDER == "EVOMI"):
        city = city.lower().rstrip().replace("-",".").replace(" ",".")
        password = f"{Config.EVOMI_PASSWORD}_country-{country}_city-{city}_session-{session[:9]}_lifetime-60"

        return {
            "mode": "http",
            "host": Config.EVOMI_HOST,
            "port": int(Config.EVOMI_PORT),
            "username": Config.EVOMI_USER_NAME,
            "password": password
        }

    return None


def get_ip_proxy(driver) -> str:
    driver.get("https://ipinfo.io/json")
    time.sleep(3)

    # ipinfo.io/json returns raw JSON as the body
    resp = driver.find_element(By.TAG_NAME, "body").text  
    data = json.loads(resp)

    proxy_ip = data.get("ip")
    print("🧠 Proxy Detected:", data)
    return proxy_ip


def getTOTP(secret_key:str) -> str:
        """Generate a TOTP (One-Time Password) using the secret key"""

        try:
            totp = pyotp.TOTP(secret_key)
            return totp.now()
        except Exception as e:
            raise Exception(
                f"TOTP generation failed", details=e)
        

def send_webhook_update(payload: dict):
    print("⏱️ Sending the webhook request for event", payload.get("event", ""))
    try:
        payload_str = json.dumps(payload)
        secret = Config.WEBHOOK_SECRET.encode()
        signature = hmac.new(secret, payload_str.encode(),
                             hashlib.sha256).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Signature": signature
        }

        webhook_url = Config.WEBHOOK_URL
        response = requests.post(
            webhook_url, headers=headers, data=payload_str)

        response.raise_for_status()
        response_data = response.json()
        print(f"📡 Webhook sent successfully")
        return response_data

    except Exception as e:
        print("Found Exception in sending webhook requests", e)
        
