from enum import StrEnum

class VariableReadValueState(StrEnum):
    FRESH = "fresh"
    MISSING = "missing"
    STALE = "stale"

    def __str__(self) -> str:
        return str(self.value)
