from enum import StrEnum

class PushSubscriptionReadPausedReasonType0(StrEnum):
    OPERATOR = "operator"
    SERVICE = "service"

    def __str__(self) -> str:
        return str(self.value)
