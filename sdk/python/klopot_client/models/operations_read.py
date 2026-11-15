from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.failed_operation import FailedOperation
  from ..models.operations_read_mqtt_item import OperationsReadMqttItem
  from ..models.operations_read_telegram_item import OperationsReadTelegramItem
  from ..models.operations_read_workers import OperationsReadWorkers
  from ..models.queue_summary import QueueSummary





T = TypeVar("T", bound="OperationsRead")



@_attrs_define
class OperationsRead:
    """ 
        Attributes:
            mqtt (list[OperationsReadMqttItem]):
            queues (list[QueueSummary]):
            recent_failures (list[FailedOperation]):
            telegram (list[OperationsReadTelegramItem]):
            workers (OperationsReadWorkers):
     """

    mqtt: list[OperationsReadMqttItem]
    queues: list[QueueSummary]
    recent_failures: list[FailedOperation]
    telegram: list[OperationsReadTelegramItem]
    workers: OperationsReadWorkers
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.failed_operation import FailedOperation # noqa: PLC0415
        from ..models.operations_read_mqtt_item import OperationsReadMqttItem # noqa: PLC0415
        from ..models.operations_read_telegram_item import OperationsReadTelegramItem # noqa: PLC0415
        from ..models.operations_read_workers import OperationsReadWorkers # noqa: PLC0415
        from ..models.queue_summary import QueueSummary # noqa: PLC0415
        mqtt = []
        for mqtt_item_data in self.mqtt:
            mqtt_item = mqtt_item_data.to_dict()
            mqtt.append(mqtt_item)



        queues = []
        for queues_item_data in self.queues:
            queues_item = queues_item_data.to_dict()
            queues.append(queues_item)



        recent_failures = []
        for recent_failures_item_data in self.recent_failures:
            recent_failures_item = recent_failures_item_data.to_dict()
            recent_failures.append(recent_failures_item)



        telegram = []
        for telegram_item_data in self.telegram:
            telegram_item = telegram_item_data.to_dict()
            telegram.append(telegram_item)



        workers = self.workers.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "mqtt": mqtt,
            "queues": queues,
            "recent_failures": recent_failures,
            "telegram": telegram,
            "workers": workers,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.failed_operation import FailedOperation # noqa: PLC0415
        from ..models.operations_read_mqtt_item import OperationsReadMqttItem # noqa: PLC0415
        from ..models.operations_read_telegram_item import OperationsReadTelegramItem # noqa: PLC0415
        from ..models.operations_read_workers import OperationsReadWorkers # noqa: PLC0415
        from ..models.queue_summary import QueueSummary # noqa: PLC0415
        d = dict(src_dict)
        mqtt = []
        _mqtt = d.pop("mqtt")
        for mqtt_item_data in (_mqtt):
            mqtt_item = OperationsReadMqttItem.from_dict(mqtt_item_data)



            mqtt.append(mqtt_item)


        queues = []
        _queues = d.pop("queues")
        for queues_item_data in (_queues):
            queues_item = QueueSummary.from_dict(queues_item_data)



            queues.append(queues_item)


        recent_failures = []
        _recent_failures = d.pop("recent_failures")
        for recent_failures_item_data in (_recent_failures):
            recent_failures_item = FailedOperation.from_dict(recent_failures_item_data)



            recent_failures.append(recent_failures_item)


        telegram = []
        _telegram = d.pop("telegram")
        for telegram_item_data in (_telegram):
            telegram_item = OperationsReadTelegramItem.from_dict(telegram_item_data)



            telegram.append(telegram_item)


        workers = OperationsReadWorkers.from_dict(d.pop("workers"))




        operations_read = cls(
            mqtt=mqtt,
            queues=queues,
            recent_failures=recent_failures,
            telegram=telegram,
            workers=workers,
        )


        operations_read.additional_properties = d
        return operations_read

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
