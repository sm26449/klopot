from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.push_subscription_read_min_severity import PushSubscriptionReadMinSeverity
from ..models.push_subscription_read_paused_reason_type_0 import PushSubscriptionReadPausedReasonType0
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="PushSubscriptionRead")



@_attrs_define
class PushSubscriptionRead:
    """ 
        Attributes:
            created_at (Any):
            enabled (bool):
            endpoint_hash (str): sha256 of the endpoint: lets a browser find its own device
            id (int):
            label (str):
            min_severity (PushSubscriptionReadMinSeverity):
            service (str): Push service host and the endpoint's tail — never the full endpoint
            consecutive_failures (int | Unset):  Default: 0.
            created_by (None | str | Unset):
            last_error (None | str | Unset):
            last_failure_at (Any | Unset):
            last_success_at (Any | Unset):
            paused_reason (None | PushSubscriptionReadPausedReasonType0 | Unset): Who paused the device: the service (after
                repeated refusals) or an operator
     """

    created_at: Any
    enabled: bool
    endpoint_hash: str
    id: int
    label: str
    min_severity: PushSubscriptionReadMinSeverity
    service: str
    consecutive_failures: int | Unset = 0
    created_by: None | str | Unset = UNSET
    last_error: None | str | Unset = UNSET
    last_failure_at: Any | Unset = UNSET
    last_success_at: Any | Unset = UNSET
    paused_reason: None | PushSubscriptionReadPausedReasonType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        enabled = self.enabled

        endpoint_hash = self.endpoint_hash

        id = self.id

        label = self.label

        min_severity = self.min_severity.value

        service = self.service

        consecutive_failures = self.consecutive_failures

        created_by: None | str | Unset
        if isinstance(self.created_by, Unset):
            created_by = UNSET
        else:
            created_by = self.created_by

        last_error: None | str | Unset
        if isinstance(self.last_error, Unset):
            last_error = UNSET
        else:
            last_error = self.last_error

        last_failure_at = self.last_failure_at

        last_success_at = self.last_success_at

        paused_reason: None | str | Unset
        if isinstance(self.paused_reason, Unset):
            paused_reason = UNSET
        elif isinstance(self.paused_reason, PushSubscriptionReadPausedReasonType0):
            paused_reason = self.paused_reason.value
        else:
            paused_reason = self.paused_reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "enabled": enabled,
            "endpoint_hash": endpoint_hash,
            "id": id,
            "label": label,
            "min_severity": min_severity,
            "service": service,
        })
        if consecutive_failures is not UNSET:
            field_dict["consecutive_failures"] = consecutive_failures
        if created_by is not UNSET:
            field_dict["created_by"] = created_by
        if last_error is not UNSET:
            field_dict["last_error"] = last_error
        if last_failure_at is not UNSET:
            field_dict["last_failure_at"] = last_failure_at
        if last_success_at is not UNSET:
            field_dict["last_success_at"] = last_success_at
        if paused_reason is not UNSET:
            field_dict["paused_reason"] = paused_reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = d.pop("created_at")

        enabled = d.pop("enabled")

        endpoint_hash = d.pop("endpoint_hash")

        id = d.pop("id")

        label = d.pop("label")

        min_severity = PushSubscriptionReadMinSeverity(d.pop("min_severity"))




        service = d.pop("service")

        consecutive_failures = d.pop("consecutive_failures", UNSET)

        def _parse_created_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        created_by = _parse_created_by(d.pop("created_by", UNSET))


        def _parse_last_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_error = _parse_last_error(d.pop("last_error", UNSET))


        last_failure_at = d.pop("last_failure_at", UNSET)

        last_success_at = d.pop("last_success_at", UNSET)

        def _parse_paused_reason(data: object) -> None | PushSubscriptionReadPausedReasonType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                paused_reason_type_0 = PushSubscriptionReadPausedReasonType0(data)



                return paused_reason_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PushSubscriptionReadPausedReasonType0 | Unset, data)

        paused_reason = _parse_paused_reason(d.pop("paused_reason", UNSET))


        push_subscription_read = cls(
            created_at=created_at,
            enabled=enabled,
            endpoint_hash=endpoint_hash,
            id=id,
            label=label,
            min_severity=min_severity,
            service=service,
            consecutive_failures=consecutive_failures,
            created_by=created_by,
            last_error=last_error,
            last_failure_at=last_failure_at,
            last_success_at=last_success_at,
            paused_reason=paused_reason,
        )


        push_subscription_read.additional_properties = d
        return push_subscription_read

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
