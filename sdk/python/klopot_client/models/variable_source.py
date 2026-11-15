from enum import StrEnum

class VariableSource(StrEnum):
    AGGREGATE = "aggregate"
    COMPUTED = "computed"
    CONSTANT = "constant"
    MQTT = "mqtt"
    SCHEDULE = "schedule"

    def __str__(self) -> str:
        return str(self.value)
