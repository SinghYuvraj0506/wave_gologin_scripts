from utils.basicHelpers import preflight_checks, heartbeat_loop
import os
from utils.WebhookUtils import WebhookUtils
from main import MainExecutor
from pyvirtualdisplay.smartdisplay import SmartDisplay
from config import Config
from dotenv import load_dotenv
import threading
load_dotenv()

def init():
    try:
        webhook = None
        webhook = WebhookUtils(task_id=Config.TASK_ID)

        stop_event = threading.Event()

        # heartbeat start -------------------
        heartbeat_thread = threading.Thread(
            target=heartbeat_loop,
            args=('', stop_event, webhook),
            daemon=True
        )
        heartbeat_thread.start()

        if not preflight_checks():
            print("❌ Preflight checks failed, exiting...")
            raise Exception("Preflight checks failed")

        with SmartDisplay() as disp:
            executor = MainExecutor(webhook=webhook)

            success = executor.execute()

            if success:
                print("✅ Execution completed successfully")
                webhook.update_task_status("task_completed")
            else:
                print("❌ Execution failed, task failed")
                webhook.update_task_status("task_failed", {
                    "task_retry": executor.need_task_retry
                })
                os.environ["SAVE_LOGS"] = "true"

    except RuntimeError as r:
        print(" ❌ Found Runtime Error >> ", str(r))
        if (webhook is not None):
            webhook.update_task_status("task_completed")

    except Exception as e:
        print(f'❌ {e}')
        os.environ["SAVE_LOGS"] = "true"

        if (webhook is not None):
            webhook.update_task_status("task_failed")
    
    finally:
        # stop heartbeat event -----------
        if stop_event is not None:
            stop_event.set()

        with open("/tmp/script_executed.flag", "w") as f:
            f.write("true")

if __name__ == '__main__':
    init()
