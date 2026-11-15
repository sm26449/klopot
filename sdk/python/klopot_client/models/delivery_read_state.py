from enum import StrEnum

class DeliveryReadState(StrEnum):
    CANCELLED = "cancelled"
    FAILED = "failed"
    PENDING = "pending"
    SENT = "sent"

    def __str__(self) -> str:
        return str(self.value)
