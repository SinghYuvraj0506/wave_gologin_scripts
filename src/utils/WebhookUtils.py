import hmac
import hashlib
import requests
import json
from config import Config
import os


class WebhookUtils:
    """
    A class to send webhook request for various events
    """

    def __init__(self, task_id: str):
        self.task_id = task_id

        taskData = self.send_webhook({
            "task_id": self.task_id,
            "event": "task_started"
        })

        if not taskData:
            raise Exception(f"Error from server, response data  is {taskData}")

        print(taskData)

        self.task_type = taskData.get("taskType")
        self.account_id = taskData.get("account_id")
        self.profile_id = taskData.get("gologin_profile_id",None)
        # self.profile_id = "687e4c10ef91c2c4838ab98d"
        self.proxy_country = taskData.get("proxy_country")
        self.proxy_city = taskData.get("proxy_city")
        self.proxy_city_fallbacks = taskData.get("proxy_city_fallbacks",None)
        self.proxy_session_id = taskData.get("proxy_session_id")
        self.attributes = taskData.get("attributes", {})

        if (not self.task_type or not self.proxy_country or not self.proxy_city or not self.proxy_session_id):
            raise Exception("Error from server, Invalid response type")

        self.check_task_response()

    def send_webhook(self, payload: dict):
        print("⏱️ Sending the webhook request for event",
              payload.get("event", ""))

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
                    webhook_url, headers=headers, data=payload_str, timeout=(
                        5, 15)
                )

            response.raise_for_status()
            response_data = response.json()
            print(f"📡 Webhook sent successfully")

            if response_data.get("stop", False):
                raise RuntimeError(
                    f"Webhook response indicated to stop: {response_data}")

            return response_data.get("data", None)

        except RuntimeError:
            raise

        except Exception as e:
            print("Found Exception in sending webhook requests", response.json())
            return False

    def check_task_response(self):
        # check if for a particular task type it has the data other wise throw error
        return True

    def update_task_status(self, event: str, payload: dict = {}):
        """
        Update the task status

        Args:
            event: 'task_failed', 'task_completed'
            payload: any extra data that need to transfer

        Returns:
            bool: Success status
        """

        return self.send_webhook({
            "task_id": self.task_id,
            "event": event,
            "payload": payload
        })

    def update_campaign_status(self, event: str, payload: dict = {}):
        """
        Update the Camapaign status

        Args:
            event: Name of event, possible options 'sent_dm', 'call_for_extra_dms'
            payload: any extra data that need to transfer poosible fields are 
                    :campaign_id, username, data, type, failed

        Returns:
            bool: Success status
        """

        return self.send_webhook({
            "task_id": self.task_id,
            "event": event,
            "payload": payload
        })

    def update_account_status(self, event: str, payload: dict = {}):
        """
        Update the Account status

        Args:
            event: 'login_completed', 'warmup_completed','login_failed', 'wrong_login_data','login_manual_interuption_required', 'login_required', 'update_profile_image'
            payload: any extra data that need to transfer

        Returns:
            bool: Success status
        """

        return self.send_webhook({
            "task_id": self.task_id,
            "event": event,
            "payload": payload,
        })
