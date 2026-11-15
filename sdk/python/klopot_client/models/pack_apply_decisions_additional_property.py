from enum import StrEnum

class PackApplyDecisionsAdditionalProperty(StrEnum):
    COPY = "copy"
    OVERWRITE = "overwrite"
    SKIP = "skip"

    def __str__(self) -> str:
        return str(self.value)
