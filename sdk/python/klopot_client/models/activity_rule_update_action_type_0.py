from enum import StrEnum

class ActivityRuleUpdateActionType0(StrEnum):
    IGNORE = "ignore"
    KEEP = "keep"

    def __str__(self) -> str:
        return str(self.value)
