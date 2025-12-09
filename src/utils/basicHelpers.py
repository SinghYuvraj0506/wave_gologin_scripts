import pyotp
from config import Config
import requests

def validate_proxy(proxy_conf: dict) -> bool:
    """
    Tries to connect to an external service using the generated proxy config.
    Returns True only if the status code is 200.
    """
    try:
        # Construct the proxy URL structure: http://user:pass@host:port
        proxy_url = f"http://{proxy_conf['username']}:{proxy_conf['password']}@{proxy_conf['host']}:{proxy_conf['port']}"

        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }

        print(f"🕵️ Validating proxy connectivity...")

        # We set a short timeout (e.g., 10s) so we don't wait forever on a bad proxy
        response = requests.get(
            "https://ipinfo.io/json",
            proxies=proxies,
            timeout=20
        )

        if response.status_code == 200:
            print("✅ Proxy validation successful.")
            return True
        else:
            print(f"❌ Proxy rejected connection. Status: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Proxy validation failed: {e}")
        return False


def build_proxyconfig(session: str, country: str, city: str) -> dict:
    proxy_config = None

    if Config.PROXY_PROVIDER == "SOAX":
        city = city.lower().rstrip()
        user = f"{Config.SOAX_USER_NAME}-country-{country}-city-{city}-sessionid-{session}-sessionlength-3600-opt-wb"

        proxy_config = {
            "mode": "http",
            "host": Config.SOAX_HOST,
            "port": int(Config.SOAX_PORT),
            "username": user,
            "password": Config.SOAX_PASSWORD
        }

    elif Config.PROXY_PROVIDER == "EVOMI":
        city = city.lower().rstrip().replace("-", ".").replace(" ", ".")
        password = f"{Config.EVOMI_PASSWORD}_country-{country}_city-{city}_session-{session[:9]}_lifetime-60"

        proxy_config = {
            "mode": "http",
            "host": Config.EVOMI_HOST,
            "port": int(Config.EVOMI_PORT),
            "username": Config.EVOMI_USER_NAME,
            "password": password
        }

    return proxy_config


def get_proxy_config(session: str, country: str, city: str, fallbacks: list[str]) -> dict:
    all_proxy_cities = [city] + fallbacks

    print(f"🔄 Attempting proxy connection for cities: {all_proxy_cities}")

    for current_city in all_proxy_cities:
        print(f"📍 Testing proxy for city: {current_city}")
        proxy_config = build_proxyconfig(session, country, current_city)

        if proxy_config:
            if validate_proxy(proxy_config):
                print(f"✅ Found working proxy in {current_city}")
                return proxy_config
            else:
                print(f"⚠️ Proxy for {current_city} is invalid/offline. Trying next...")
        else:
             print(f"⚠️ Failed to build config for {current_city}")

    print("❌ All proxy cities (main + fallbacks) failed.")
    return None


def getTOTP(secret_key: str) -> str:
    """Generate a TOTP (One-Time Password) using the secret key"""

    try:
        totp = pyotp.TOTP(secret_key)
        return totp.now()
    except Exception as e:
        raise Exception(
            f"TOTP generation failed", details=e)
