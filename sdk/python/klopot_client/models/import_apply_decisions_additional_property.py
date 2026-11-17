from enum import StrEnum

class ImportApplyDecisionsAdditionalProperty(StrEnum):
    COPY = "copy"
    IMPORT = "import"
    OVERWRITE = "overwrite"
    SKIP = "skip"

    def __str__(self) -> str:
        return str(self.value)
