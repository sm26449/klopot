from enum import StrEnum

class ActivityRuleUpdateRequestBodyType0(StrEnum):
    ALWAYS = "always"
    AUTO = "auto"
    ERRORS = "errors"
    NEVER = "never"

    def __str__(self) -> str:
        return str(self.value)
