from enum import StrEnum

class RuleRunState(StrEnum):
    ERROR = "error"
    FIRING = "firing"
    INACTIVE = "inactive"
    NO_DATA = "no_data"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
