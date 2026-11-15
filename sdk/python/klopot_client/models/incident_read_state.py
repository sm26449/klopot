from enum import StrEnum

class IncidentReadState(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"

    def __str__(self) -> str:
        return str(self.value)
