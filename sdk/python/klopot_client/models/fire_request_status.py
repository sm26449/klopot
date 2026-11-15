from enum import StrEnum

class FireRequestStatus(StrEnum):
    FIRING = "firing"
    RESOLVED = "resolved"

    def __str__(self) -> str:
        return str(self.value)
