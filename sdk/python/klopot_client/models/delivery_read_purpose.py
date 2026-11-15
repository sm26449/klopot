from enum import StrEnum

class DeliveryReadPurpose(StrEnum):
    ESCALATION = "escalation"
    NOTIFICATION = "notification"

    def __str__(self) -> str:
        return str(self.value)
