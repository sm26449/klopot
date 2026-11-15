from enum import StrEnum

class IncidentDetailState(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"

    def __str__(self) -> str:
        return str(self.value)
