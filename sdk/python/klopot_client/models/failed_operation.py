from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="FailedOperation")



@_attrs_define
class FailedOperation:
    """ 
        Attributes:
            attempts (int):
            channel (str):
            created_at (None | str):
            error (None | str):
            notification_id (str):
            queue (str):
     """

    attempts: int
    channel: str
    created_at: None | str
    error: None | str
    notification_id: str
    queue: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        attempts = self.attempts

        channel = self.channel

        created_at: None | str
        created_at = self.created_at

        error: None | str
        error = self.error

        notification_id = self.notification_id

        queue = self.queue


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "attempts": attempts,
            "channel": channel,
            "created_at": created_at,
            "error": error,
            "notification_id": notification_id,
            "queue": queue,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        attempts = d.pop("attempts")

        channel = d.pop("channel")

        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        def _parse_error(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        error = _parse_error(d.pop("error"))


        notification_id = d.pop("notification_id")

        queue = d.pop("queue")

        failed_operation = cls(
            attempts=attempts,
            channel=channel,
            created_at=created_at,
            error=error,
            notification_id=notification_id,
            queue=queue,
        )


        failed_operation.additional_properties = d
        return failed_operation

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
