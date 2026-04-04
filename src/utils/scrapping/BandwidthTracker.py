from time import time
import json
import threading
from collections import defaultdict


class BandwidthTracker:

    def __init__(self, driver):
        self.driver = driver
        self._current_action = "idle"
        self._lock = threading.Lock()
        self._stats = defaultdict(lambda: {"requests": 0, "bytes": 0})
        self._running = False
        self._thread = None

    def start(self):
        """Call once after bandwidth_manager.enable()"""
        self._running = True
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def set_action(self, label: str):
        with self._lock:
            self._current_action = label

    def _poll(self):
        while self._running:
            try:
                logs = self.driver.get_log("performance")
                for entry in logs:
                    try:
                        msg = json.loads(entry["message"])["message"]
                        if msg.get("method") == "Network.loadingFinished":
                            encoded_bytes = msg["params"].get("encodedDataLength", 0)
                            if encoded_bytes > 0:
                                with self._lock:
                                    action = self._current_action
                                    self._stats[action]["requests"] += 1
                                    self._stats[action]["bytes"] += encoded_bytes
                    except Exception:
                        continue
            except Exception:
                pass
            time.sleep(2)  # slow poll — just draining the buffer, not time sensitive

    def print_report(self):
        with self._lock:
            report = dict(self._stats)

        if not report:
            print("📊 No data recorded yet.")
            return

        total_bytes = sum(v["bytes"] for v in report.values())
        print("\n📊 Bandwidth Report (actual proxy usage)")
        print(f"{'Action':<30} {'Requests':>10} {'Data':>12}")
        print("-" * 55)
        for action, data in sorted(report.items(), key=lambda x: -x[1]["bytes"]):
            mb = data["bytes"] / 1024 / 1024
            kb = data["bytes"] / 1024
            size_str = f"{mb:.3f} MB" if mb >= 1 else f"{kb:.2f} KB"
            print(f"{action:<30} {data['requests']:>10} {size_str:>12}")
        print("-" * 55)
        print(f"{'TOTAL':<30} {'':>10} {total_bytes/1024/1024:>10.3f} MB\n")