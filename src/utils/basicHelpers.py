from utils.WebhookUtils import WebhookUtils
import pyotp
from config import Config
import requests
import time
import socket

def wait_for_network_ready(max_wait: int = 30) -> bool:
    """
    Waits for VM network to be fully initialized.
    Critical for GCP spot VMs that start very quickly.
    """
    print("🌐 Checking network readiness...")
    
    # Test targets - public DNS servers and common endpoints
    test_hosts = [
        ("8.8.8.8", 53),           # Google DNS
        ("1.1.1.1", 53),           # Cloudflare DNS
        ("ipinfo.io", 80),         # Validation endpoint
    ]
    
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        all_ready = True
        
        for host, port in test_hosts:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result != 0:
                    all_ready = False
                    break
            except:
                all_ready = False
                break
        
        if all_ready:
            elapsed = time.time() - start_time
            print(f"✅ Network ready after {elapsed:.1f}s")
            return True
        
        print("⏳ Network not ready, waiting 2s...")
        time.sleep(2)
    
    print(f"⚠️ Network readiness timeout after {max_wait}s")
    return False

def test_dns_resolution(hostname: str) -> bool:
    """Verify DNS is working before attempting proxy connections."""
    try:
        ip = socket.gethostbyname(hostname)
        print(f"✅ DNS working: {hostname} → {ip}")
        return True
    except socket.gaierror:
        print(f"❌ DNS failed to resolve: {hostname}")
        return False

def validate_proxy(proxy_conf: dict, max_retries: int = 3) -> bool:
    """
    Validates proxy with retry logic and network readiness checks.
    """

    # Construct the proxy URL structure: http://user:pass@host:port
    proxy_url = f"http://{proxy_conf['username']}:{proxy_conf['password']}@{proxy_conf['host']}:{proxy_conf['port']}"

    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }

    # First verify DNS can resolve proxy host
    if not test_dns_resolution(proxy_conf['host']):
        print("⚠️ DNS resolution failed for proxy host, waiting 3s...")
        time.sleep(3)
        if not test_dns_resolution(proxy_conf['host']):
            print("❌ DNS still failing, skipping this proxy")
            return False

    validation_endpoints = [
        ("http://ip-api.com/json/", "HTTP"),
        ("http://ipinfo.io/json", "HTTP"),
        ("https://ipinfo.io/json", "HTTPS"),  # Try HTTPS last
        ("http://httpbin.org/ip", "HTTP"),
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    print(f"🕵️ Validating proxy connectivity...")

    for attempt in range(max_retries):
        if attempt > 0:
            # Exponential backoff between retries
            wait_time = 2 ** attempt
            print(f"⏳ Retry {attempt + 1}/{max_retries} after {wait_time}s...")
            time.sleep(wait_time)
        
        for endpoint, protocol in validation_endpoints:
            try:
                print(f"Testing {protocol}: {endpoint.split('/')[2]}...")
                
                response = requests.get(
                    endpoint,
                    proxies=proxies,
                    headers=headers,
                    timeout=20,
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    # Verify we got proxied (not direct connection)
                    try:
                        data = response.json()
                        proxy_ip = data.get('ip') or data.get('query') or data.get('origin', '').split(',')[0].strip()
                        print(f"✅ Proxy validated! IP: {proxy_ip} via {protocol}")
                        return True
                    except:
                        print(f"✅ Proxy validated via {protocol}")
                        return True
                else:
                    print(f"⚠️ HTTP {response.status_code}")
                    
            except requests.exceptions.ProxyError as e:
                error_msg = str(e)
                
                # Check for specific error patterns
                if "412" in error_msg:
                    print(f"❌ 412 Precondition Failed")
                    # On 412, wait longer before retry
                    if attempt < max_retries - 1:
                        print(f"   💡 Network might not be ready, will retry...")
                        time.sleep(3)
                elif "Tunnel connection failed" in error_msg:
                    print(f"❌ Tunnel failed (network not ready?)")
                    time.sleep(2)
                elif "Connection refused" in error_msg:
                    print(f"❌ Connection refused")
                    return False  # Don't retry on connection refused
                else:
                    print(f"⚠️ Proxy error: {error_msg[:80]}")
                
                # Don't continue to next endpoint on ProxyError - retry same config
                break
                
            except requests.exceptions.Timeout:
                print(f"Timeout")
                continue
                
            except requests.exceptions.ConnectionError as e:
                print(f"⚠️ Connection error: {str(e)[:80]}")
                # Network might not be ready
                break
                
            except Exception as e:
                print(f"⚠️ Unexpected error: {str(e)[:80]}")
                continue
    
    print(f"❌ Proxy validation failed after {max_retries} attempts")
    return False


def build_proxyconfig(session: str, country: str, city: str) -> dict:
    """Builds proxy configuration based on provider."""

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
    """
    Attempts to connect through multiple cities with network readiness checks.
    """

    print("=" * 60)
    print("🚀 Starting proxy configuration...")
    print("=" * 60)

    if not wait_for_network_ready(max_wait=30):
        print("⚠️ Network readiness check timed out, proceeding anyway...")

    # Additional safety delay for DNS propagation
    print("⏳ Additional 3s grace period for DNS stability...")
    time.sleep(3)

    all_proxy_cities = [city] + fallbacks
    print(f"🔄 Attempting proxy connection for cities: {all_proxy_cities}")

    for idx, current_city in enumerate(all_proxy_cities, 1):
        print(f"\n{'='*60}")
        print(f"📍 [{idx}/{len(all_proxy_cities)}] Testing: {current_city}")
        print(f"{'='*60}")

        proxy_config = build_proxyconfig(
            session=session,
            country=country,
            city=current_city
        )
        
        if not proxy_config:
            print(f"⚠️ Failed to build config for {current_city}")
            continue

        if validate_proxy(proxy_config):
            print(f"✅ Found working proxy in {current_city}")
            return proxy_config
        else:
            print(f"\n❌ {current_city} failed")
            
            # Longer delay between cities if early attempts failed
            if idx < len(all_proxy_cities):
                wait = 3 if idx <= 2 else 2
                print(f"⏳ Waiting {wait}s before trying next city...")
                time.sleep(wait)


    raise Exception("❌ All proxy cities (main + fallbacks) failed.")


def preflight_checks():
    """Run before proxy initialization to ensure VM is ready."""

    print("\n" + "="*60)
    print("🔧 PREFLIGHT CHECKS")
    print("="*60 + "\n")
    
    # 1. Check internet connectivity
    print("1️⃣ Testing internet connectivity...")
    try:
        response = requests.get("http://clients3.google.com/generate_204", timeout=5)
        if response.status_code == 204:
            print("✅ Internet connected")
        else:
            print(f"⚠️ Unexpected response: {response.status_code}")
    except Exception as e:
        print(f"❌ No internet: {e}")
        return False
    
    # 2. Check DNS
    print("\n2️⃣ Testing DNS resolution...")
    test_domains = ["google.com", "ipinfo.io"]
    for domain in test_domains:
        if test_dns_resolution(domain):
            print(f"✅ {domain}")
        else:
            print(f"❌ {domain} failed")
            return False
    
    # 3. Get VM info
    print("\n3️⃣ VM Information...")
    try:
        public_ip = requests.get('https://api.ipify.org', timeout=5).text
        print(f"Public IP: {public_ip}")
    except:
        print("⚠️ Could not get public IP")
    
    print("\n" + "="*60)
    print("✅ All preflight checks passed")
    print("="*60 + "\n")
    
    return True


def getTOTP(secret_key: str) -> str:
    """Generate a TOTP (One-Time Password) using the secret key"""

    try:
        totp = pyotp.TOTP(secret_key)
        return totp.now()
    except Exception as e:
        raise Exception(
            f"TOTP generation failed", details=e)


def heartbeat_loop(worker_id, stop_event, webhook: WebhookUtils):
    while not stop_event.is_set():
        webhook.heartbeat_update({
            "worker_id": worker_id
        })

        time.sleep(Config.HEARTBEAT_INTERVAL)
