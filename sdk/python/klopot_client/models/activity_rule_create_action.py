from enum import StrEnum

class ActivityRuleCreateAction(StrEnum):
    IGNORE = "ignore"
    KEEP = "keep"

    def __str__(self) -> str:
        return str(self.value)
