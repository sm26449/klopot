from enum import StrEnum

class ListRulesV1RulesGetEvalStatusType0(StrEnum):
    ERROR = "error"
    NO_DATA = "no_data"
    OK = "ok"

    def __str__(self) -> str:
        return str(self.value)
