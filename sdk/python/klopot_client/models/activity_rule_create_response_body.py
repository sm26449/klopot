from enum import StrEnum

class ActivityRuleCreateResponseBody(StrEnum):
    ALWAYS = "always"
    AUTO = "auto"
    ERRORS = "errors"
    NEVER = "never"

    def __str__(self) -> str:
        return str(self.value)
