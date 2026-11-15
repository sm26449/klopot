from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="AttemptRead")



@_attrs_define
class AttemptRead:
    """ 
        Attributes:
            attempt_no (Any):
            channel (Any):
            duration_ms (Any):
            id (Any):
            kind (Any):
            outcome (Any):
            started_at (Any):
            delivery_id (Any | Unset):
            error (Any | Unset):
            exchange (Any | Unset): HTTP exchanges of the attempt; bodies only for the `admin` scope.
            http_status (Any | Unset):
            notification_id (Any | Unset):
            provider_ref (Any | Unset):
            retry_after_sec (Any | Unset):
     """

    attempt_no: Any
    channel: Any
    duration_ms: Any
    id: Any
    kind: Any
    outcome: Any
    started_at: Any
    delivery_id: Any | Unset = UNSET
    error: Any | Unset = UNSET
    exchange: Any | Unset = UNSET
    http_status: Any | Unset = UNSET
    notification_id: Any | Unset = UNSET
    provider_ref: Any | Unset = UNSET
    retry_after_sec: Any | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        attempt_no = self.attempt_no

        channel = self.channel

        duration_ms = self.duration_ms

        id = self.id

        kind = self.kind

        outcome = self.outcome

        started_at = self.started_at

        delivery_id = self.delivery_id

        error = self.error

        exchange = self.exchange

        http_status = self.http_status

        notification_id = self.notification_id

        provider_ref = self.provider_ref

        retry_after_sec = self.retry_after_sec


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "attempt_no": attempt_no,
            "channel": channel,
            "duration_ms": duration_ms,
            "id": id,
            "kind": kind,
            "outcome": outcome,
            "started_at": started_at,
        })
        if delivery_id is not UNSET:
            field_dict["delivery_id"] = delivery_id
        if error is not UNSET:
            field_dict["error"] = error
        if exchange is not UNSET:
            field_dict["exchange"] = exchange
        if http_status is not UNSET:
            field_dict["http_status"] = http_status
        if notification_id is not UNSET:
            field_dict["notification_id"] = notification_id
        if provider_ref is not UNSET:
            field_dict["provider_ref"] = provider_ref
        if retry_after_sec is not UNSET:
            field_dict["retry_after_sec"] = retry_after_sec

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        attempt_no = d.pop("attempt_no")

        channel = d.pop("channel")

        duration_ms = d.pop("duration_ms")

        id = d.pop("id")

        kind = d.pop("kind")

        outcome = d.pop("outcome")

        started_at = d.pop("started_at")

        delivery_id = d.pop("delivery_id", UNSET)

        error = d.pop("error", UNSET)

        exchange = d.pop("exchange", UNSET)

        http_status = d.pop("http_status", UNSET)

        notification_id = d.pop("notification_id", UNSET)

        provider_ref = d.pop("provider_ref", UNSET)

        retry_after_sec = d.pop("retry_after_sec", UNSET)

        attempt_read = cls(
            attempt_no=attempt_no,
            channel=channel,
            duration_ms=duration_ms,
            id=id,
            kind=kind,
            outcome=outcome,
            started_at=started_at,
            delivery_id=delivery_id,
            error=error,
            exchange=exchange,
            http_status=http_status,
            notification_id=notification_id,
            provider_ref=provider_ref,
            retry_after_sec=retry_after_sec,
        )


        attempt_read.additional_properties = d
        return attempt_read

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
