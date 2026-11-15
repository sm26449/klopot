from enum import StrEnum

class ChannelKind(StrEnum):
    BANNER = "banner"
    EMAIL = "email"
    GOTIFY = "gotify"
    MQTT = "mqtt"
    NTFY = "ntfy"
    PUSH = "push"
    PUSHOVER = "pushover"
    SMS = "sms"
    TELEGRAM = "telegram"
    UI = "ui"
    WEBHOOK = "webhook"

    def __str__(self) -> str:
        return str(self.value)
