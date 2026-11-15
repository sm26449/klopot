from enum import StrEnum

class PushSubscriptionUpdateMinSeverityType0(StrEnum):
    CRITICAL = "critical"
    INFO = "info"
    WARNING = "warning"

    def __str__(self) -> str:
        return str(self.value)
