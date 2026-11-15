from enum import StrEnum

class ComponentHealthStatus(StrEnum):
    DEGRADED = "degraded"
    DOWN = "down"
    OK = "ok"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return str(self.value)
