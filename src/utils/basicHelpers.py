import time
import pyotp
from config import Config
import json
from selenium.webdriver.common.by import By
import hmac
import hashlib
import requests

def build_proxyconfig(session:str, country:str, city:str) -> dict:
    user = f"{Config.SOAX_USER_NAME}-country-{country}-city-{city}-sessionid-{session}-sessionlength-3600-opt-wb"

    return {
        "mode": "http",
        "host": "proxy.soax.com",
        "port": 5000,
        "username": user,
        "password": Config.SOAX_PASSWORD
    }


def get_ip_proxy(driver) -> str:
    driver.get("https://ipinfo.io/json")
    time.sleep(3)
    resp = driver.find_element(By.TAG_NAME, "pre").text
    data = json.loads(resp)
    proxy_ip = data["ip"]
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
        
