import threading
from collections import defaultdict


class BandwidthTracker:
    """
    Passive bandwidth tracker. Piggybacks on Network.enable already called
    by BandwidthManager. No polling thread — reads logs only when you 
    explicitly call snapshot(), so zero background load.
    """

    def __init__(self, driver):
        self.driver = driver
        self._current_action = "idle"
        self._lock = threading.Lock()
        self._stats = defaultdict(lambda: {"requests": 0, "bytes": 0})

    def set_action(self, label: str):
        with self._lock:
            self._current_action = label

    def snapshot(self):
        """
        Call this manually at checkpoints — reads performance log once
        and attributes bytes to current action. No background thread.
        """
        import json
        try:
            logs = self.driver.get_log("performance")
            for entry in logs:
                msg = json.loads(entry["message"])["message"]
                if msg.get("method") == "Network.loadingFinished":
                    encoded_bytes = msg.get("params", {}).get("encodedDataLength", 0)
                    with self._lock:
                        action = self._current_action
                    self._stats[action]["requests"] += 1
                    self._stats[action]["bytes"] += encoded_bytes
        except Exception:
            pass

    def report(self) -> dict:
        with self._lock:
            result = {}
            for action, data in self._stats.items():
                result[action] = {
                    "requests": data["requests"],
                    "bytes": data["bytes"],
                    "kb": round(data["bytes"] / 1024, 2),
                    "mb": round(data["bytes"] / 1024 / 1024, 3),
                }
            return result

    def print_report(self):
        report = self.report()
        total_bytes = sum(v["bytes"] for v in report.values())
        print("\n📊 Bandwidth Report")
        print(f"{'Action':<30} {'Requests':>10} {'Size':>12}")
        print("-" * 55)
        for action, data in sorted(report.items(), key=lambda x: -x[1]["bytes"]):
            size_str = f"{data['mb']} MB" if data["mb"] >= 1 else f"{data['kb']} KB"
            print(f"{action:<30} {data['requests']:>10} {size_str:>12}")
        print("-" * 55)
        total_mb = round(total_bytes / 1024 / 1024, 3)
        print(f"{'TOTAL':<30} {'':>10} {total_mb:>11} MB\n")