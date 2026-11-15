from enum import StrEnum

class ListIncidentsV1IncidentsGetStateType0(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"

    def __str__(self) -> str:
        return str(self.value)
