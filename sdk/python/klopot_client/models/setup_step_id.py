from enum import StrEnum

class SetupStepId(StrEnum):
    CHANNEL = "channel"
    CHANNEL_TESTED = "channel_tested"
    FIRST_ALERT = "first_alert"
    RULES = "rules"
    SOURCE = "source"

    def __str__(self) -> str:
        return str(self.value)
