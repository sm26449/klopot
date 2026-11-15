from enum import StrEnum

class ListVariablesV1VariablesGetStateType0(StrEnum):
    FRESH = "fresh"
    MISSING = "missing"
    STALE = "stale"

    def __str__(self) -> str:
        return str(self.value)
