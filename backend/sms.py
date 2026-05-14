import logging
from twilio.rest import Client

logger = logging.getLogger(__name__)

class SMSClient:
    def __init__(self, account_sid: str, auth_token: str, from_number: str, to_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.to_number = to_number

    def send(self, message: str):
        if not all([self.account_sid, self.auth_token, self.from_number, self.to_number]):
            logger.warning("SMS not configured — skipping send")
            return
        try:
            client = Client(self.account_sid, self.auth_token)
            client.messages.create(
                body=message,
                from_=self.from_number,
                to=self.to_number,
            )
        except Exception as e:
            logger.error(f"SMS send failed: {e}")
