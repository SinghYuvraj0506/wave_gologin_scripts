from main import MainExecutor
from pyvirtualdisplay.smartdisplay import SmartDisplay
import sys
from config import Config
from dotenv import load_dotenv
load_dotenv()
from utils.WebhookUtils import WebhookUtils


def init():
    webhook = WebhookUtils(task_id=Config.TASK_ID)

    with SmartDisplay() as disp:
        executor = MainExecutor(profile_id=webhook.profile_id, proxy_country=webhook.proxy_country,
                                proxy_city=webhook.proxy_city, session_id=webhook.proxy_session_id, task_type=webhook.task_type, webhook=webhook, extra_attributes=webhook.attributes)

        success = executor.execute()

        if success:
            print("✅ Execution completed successfully")
            webhook.update_task_status("task_completed")
        else:
            print("❌ Execution failed")
            webhook.update_task_status("task_failed")


if __name__ == '__main__':
    try:
        init()
    except Exception as e:
        print(f'❌ {e}')
        sys.exit(1)
