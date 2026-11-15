from enum import StrEnum

class SnoozeReadScope(StrEnum):
    CHANNEL = "channel"
    RULE = "rule"
    TYPE = "type"

    def __str__(self) -> str:
        return str(self.value)
