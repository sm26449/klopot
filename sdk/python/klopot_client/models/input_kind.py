from enum import StrEnum

class InputKind(StrEnum):
    ALERTMANAGER = "alertmanager"
    EMAIL_IMAP = "email_imap"
    HTTP_POLL = "http_poll"
    MQTT = "mqtt"
    SCHEDULE = "schedule"
    SMS_INBOX = "sms_inbox"
    WEBHOOK = "webhook"

    def __str__(self) -> str:
        return str(self.value)
