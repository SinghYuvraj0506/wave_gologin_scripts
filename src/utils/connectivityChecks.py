import requests
import socket
import time
from dataclasses import dataclass
from typing import Optional

CONNECTIVITY_TIMEOUT = 10  # seconds per request

@dataclass
class ConnectivityResult:
    success: bool

    # Layer 1 — Direct internet
    internet_ok: bool = False
    internet_latency_ms: Optional[int] = None

    # Layer 2 — Proxy
    proxy_ok: bool = False
    proxy_ip: Optional[str] = None
    proxy_latency_ms: Optional[int] = None

    # Layer 3 — Instagram via proxy
    instagram_ok: bool = False
    instagram_load_ms: Optional[int] = None
    instagram_status_code: Optional[int] = None

    # Failure info
    failed_at: Optional[str] = None   # "internet" | "proxy" | "instagram"
    failure_reason: Optional[str] = None

    def summary(self) -> str:
        if self.success:
            return (
                f"✅ All checks passed | "
                f"internet={self.internet_latency_ms}ms | "
                f"proxy={self.proxy_latency_ms}ms (IP: {self.proxy_ip}) | "
                f"instagram={self.instagram_load_ms}ms"
            )
        return (
            f"❌ Failed at [{self.failed_at}] | "
            f"reason={self.failure_reason} | "
            f"internet_ok={self.internet_ok} | "
            f"proxy_ok={self.proxy_ok} | "
            f"instagram_ok={self.instagram_ok}"
        )


def check_connectivity(
    proxy_host: str,
    proxy_port: int,
    proxy_user: str,
    proxy_pass: str,
    instagram_slow_threshold_ms: int = 6000,
) -> ConnectivityResult:
    """
    Checks connectivity in 3 layers:
      1. Direct internet (DNS + ping via socket)
      2. Proxy health (ip-api.com through proxy)
      3. Instagram reachability + load time (through proxy)

    Returns:
        ConnectivityResult with success=True only if all 3 pass.
    """

    result = ConnectivityResult(success=False)
    proxy_dict = {
        "http":  f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}",
        "https": f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}",
    }

    # ── Layer 1: Direct internet (DNS resolution + TCP connect to 8.8.8.8) ──
    print("🔎 [1/3] Checking direct internet connectivity...")
    try:
        start = time.time()
        # TCP connect to Google DNS — no HTTP, just raw socket
        sock = socket.create_connection(("8.8.8.8", 53), timeout=CONNECTIVITY_TIMEOUT)
        sock.close()
        latency_ms = int((time.time() - start) * 1000)

        result.internet_ok = True
        result.internet_latency_ms = latency_ms
        print(f"   ✅ Internet OK | latency: {latency_ms}ms")

    except OSError as e:
        result.failed_at = "internet"
        result.failure_reason = f"Socket error: {e}"
        print(f"   ❌ Internet unreachable: {e}")
        return result

    # ── Layer 2: Proxy health ─────────────────────────────────────────────────
    print("🔎 [2/3] Checking proxy health...")
    try:
        start = time.time()
        resp = requests.get(
            "http://ip-api.com/json",
            proxies=proxy_dict,
            timeout=CONNECTIVITY_TIMEOUT
        )
        latency_ms = int((time.time() - start) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            proxy_ip = data.get("query", "unknown")
            proxy_country = data.get("country", "unknown")
            proxy_city = data.get("city", "unknown")

            result.proxy_ok = True
            result.proxy_ip = proxy_ip
            result.proxy_latency_ms = latency_ms
            print(f"   ✅ Proxy OK | IP: {proxy_ip} ({proxy_city}, {proxy_country}) | latency: {latency_ms}ms")
        else:
            result.failed_at = "proxy"
            result.failure_reason = f"ip-api returned HTTP {resp.status_code}"
            print(f"   ❌ Proxy check failed: HTTP {resp.status_code}")
            return result

    except requests.exceptions.ProxyError as e:
        result.failed_at = "proxy"
        result.failure_reason = f"ProxyError: {e}"
        print(f"   ❌ Proxy unreachable: {e}")
        return result

    except requests.exceptions.ConnectTimeout:
        result.failed_at = "proxy"
        result.failure_reason = "Proxy connection timed out"
        print("   ❌ Proxy timed out")
        return result

    except Exception as e:
        result.failed_at = "proxy"
        result.failure_reason = f"Unexpected error: {e}"
        print(f"   ❌ Proxy check error: {e}")
        return result

    # ── Layer 3: Instagram via proxy ──────────────────────────────────────────
    print("🔎 [3/3] Checking Instagram reachability through proxy...")
    try:
        start = time.time()
        resp = requests.get(
            "https://www.instagram.com",
            proxies=proxy_dict,
            timeout=CONNECTIVITY_TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        load_ms = int((time.time() - start) * 1000)

        result.instagram_status_code = resp.status_code
        result.instagram_load_ms = load_ms

        if resp.status_code != 200:
            result.failed_at = "instagram"
            result.failure_reason = f"Instagram returned HTTP {resp.status_code}"
            print(f"   ❌ Instagram returned HTTP {resp.status_code}")
            return result

        if load_ms > instagram_slow_threshold_ms:
            result.failed_at = "instagram"
            result.failure_reason = f"Instagram too slow: {load_ms}ms (threshold: {instagram_slow_threshold_ms}ms)"
            print(f"   ❌ Instagram too slow: {load_ms}ms")
            return result

        result.instagram_ok = True
        print(f"   ✅ Instagram OK | load: {load_ms}ms | status: {resp.status_code}")

    except requests.exceptions.ConnectTimeout:
        result.failed_at = "instagram"
        result.failure_reason = "Instagram connection timed out through proxy"
        print("   ❌ Instagram timed out through proxy")
        return result

    except Exception as e:
        result.failed_at = "instagram"
        result.failure_reason = f"Unexpected error: {e}"
        print(f"   ❌ Instagram check error: {e}")
        return result

    # ── All passed ────────────────────────────────────────────────────────────
    result.success = True
    print(f"📡 Connectivity check complete: {result.summary()}")
    return result