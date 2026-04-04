import threading
import time

class BandwidthManager:
    """
    This class is used to block all the media files from loading on the page.
    """

    def __init__(self):
        self._intercept_thread = None
        self._intercepting = False

    def enable(self, driver = None):
        if(driver is not None):
            self.driver = driver

        # Step 1 — Enable CDP domains
        self.driver.execute_cdp_cmd("Network.enable", {})
        self.driver.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})

        # # Step 2 — Enable Fetch interception for target domains
        # self.driver.execute_cdp_cmd("Fetch.enable", {
        #     "patterns": [
        #         {"urlPattern": "*fna.fbcdn.net*","requestStage": "Request"},
        #         {"urlPattern": "*scontent*.cdninstagram.com*", "requestStage": "Request"},
        #     ]
        # })

        # # Step 3 — Start background thread to fulfill paused requests
        # self._intercepting = True
        # self._intercept_thread = threading.Thread(
        #     target=self._handle_paused_requests,
        #     daemon=True
        # )
        # self._intercept_thread.start()

        # Step 4 — Inject JS as safety net
        self._inject_js_interceptor()

        print("🚫 Bandwidth saver enabled.")

    def disable(self):
        self._intercepting = False
        try:
            self.driver.execute_cdp_cmd("Fetch.disable", {})
            self.driver.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": False})
        except:
            pass
        print("✅ Bandwidth saver disabled.")

    def _handle_paused_requests(self):
        """
        Poll for Fetch.requestPaused events and fulfill them with empty 200.
        This runs in a background thread.
        """
        while self._intercepting:
            try:
                # Get all paused requests
                logs = self.driver.get_log("performance")
                for entry in logs:
                    import json
                    msg = json.loads(entry["message"])["message"]

                    if msg.get("method") == "Fetch.requestPaused":
                        request_id = msg["params"]["requestId"]
                        url = msg["params"]["request"]["url"]

                        # print(f"🛑 Intercepted: {url}")

                        # Fulfill with empty 200 — Instagram won't retry this
                        self.driver.execute_cdp_cmd("Fetch.fulfillRequest", {
                            "requestId": request_id,
                            "responseCode": 200,
                            "responseHeaders": self._get_fake_headers(url),
                            "body": ""  # base64 encoded body — empty string = no content
                        })

            except Exception as e:
                # Driver may not be ready yet, just keep polling
                pass

            time.sleep(0.5)  # 50ms poll interval — adjust as needed


    def _inject_js_interceptor(self):
        """
        Inject JS to catch anything that slips past CDP.
        Re-inject on every page navigation.
        """
        script = """
        (function () {
            if (window.__bwInterceptorActive) return;
            window.__bwInterceptorActive = true;

            const isTarget = (url) =>
                typeof url === "string" && (
                    url.includes("fna.fbcdn.net") ||
                    /scontent[^.]*\.cdninstagram\.com/.test(url)
                );

            const emptyBlob = URL.createObjectURL(
                new Blob([""], { type: "text/plain" })
            );

            // Block fetch
            const origFetch = window.fetch;
            window.fetch = async function (...args) {
                const url = typeof args[0] === "string" ? args[0] : args[0]?.url;
                if (isTarget(url)) {
                    return new Response(new Blob(), { status: 200 });
                }
                return origFetch.apply(this, args);
            };

            // Block XHR
            const origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function (method, url, ...rest) {
                this._blocked = isTarget(url);
                return origOpen.call(this, method, url, ...rest);
            };
            const origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = function (...args) {
                if (this._blocked) {
                    Object.defineProperty(this, "readyState", { value: 4 });
                    Object.defineProperty(this, "status",    { value: 200 });
                    setTimeout(() => {
                        this.onload?.();
                        this.onreadystatechange?.();
                    }, 0);
                    return;
                }
                return origSend.apply(this, args);
            };

            // Block img/video src
            const patchSrc = (proto) => {
                const desc = Object.getOwnPropertyDescriptor(proto, "src");
                if (!desc?.set) return;
                Object.defineProperty(proto, "src", {
                    set(v) { desc.set.call(this, isTarget(v) ? emptyBlob : v); },
                    get: desc.get,
                    configurable: true
                });
            };
            patchSrc(HTMLImageElement.prototype);
            patchSrc(HTMLVideoElement.prototype);
            patchSrc(HTMLSourceElement.prototype);

            // MutationObserver for dynamic DOM
            new MutationObserver((mutations) => {
                for (const m of mutations) {
                    for (const node of m.addedNodes) {
                        if (node.nodeType !== 1) continue;
                        ["src", "srcset", "poster"].forEach(attr => {
                            const val = node.getAttribute?.(attr);
                            if (val && isTarget(val)) node.setAttribute(attr, "");
                        });
                    }
                }
            }).observe(document.documentElement, { childList: true, subtree: true });

            console.log("✅ BW Interceptor active");
        })();
        """
        self.driver.execute_script(script)

    
    def _get_fake_headers(self, url: str) -> list:
        if ".mp4" in url or "video" in url:
            content_type = "video/mp4"
        elif ".m3u8" in url:
            content_type = "application/x-mpegURL"
        elif ".webm" in url:
            content_type = "video/webm"
        elif ".jpg" in url or ".jpeg" in url:
            content_type = "image/jpeg"
        elif ".png" in url:
            content_type = "image/png"
        elif ".webp" in url:
            content_type = "image/webp"
        elif "cdninstagram.com" in url:
            content_type = "image/jpeg"  # ← default for instagram CDN, mostly JPEGs
        else:
            content_type = "application/octet-stream"

        return [
            {"name": "Access-Control-Allow-Origin",      "value": "*"},
            {"name": "Access-Control-Allow-Credentials", "value": "true"},
            {"name": "Access-Control-Allow-Methods",     "value": "GET, OPTIONS"},
            {"name": "Access-Control-Allow-Headers",     "value": "Range, Accept-Encoding"},
            {"name": "Access-Control-Expose-Headers",    "value": "Content-Length, Content-Range"},
            {"name": "Content-Type",                     "value": content_type},
            {"name": "Content-Length",                   "value": "0"},
            {"name": "Accept-Ranges",                    "value": "bytes"},
            {"name": "Cache-Control",                    "value": "max-age=3600, public"},
            {"name": "Timing-Allow-Origin",              "value": "*"},
        ]