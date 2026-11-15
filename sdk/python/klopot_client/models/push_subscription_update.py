from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.push_subscription_update_min_severity_type_0 import PushSubscriptionUpdateMinSeverityType0
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="PushSubscriptionUpdate")



@_attrs_define
class PushSubscriptionUpdate:
    """ 
        Attributes:
            enabled (bool | None | Unset):
            label (None | str | Unset):
            min_severity (None | PushSubscriptionUpdateMinSeverityType0 | Unset):
     """

    enabled: bool | None | Unset = UNSET
    label: None | str | Unset = UNSET
    min_severity: None | PushSubscriptionUpdateMinSeverityType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        label: None | str | Unset
        if isinstance(self.label, Unset):
            label = UNSET
        else:
            label = self.label

        min_severity: None | str | Unset
        if isinstance(self.min_severity, Unset):
            min_severity = UNSET
        elif isinstance(self.min_severity, PushSubscriptionUpdateMinSeverityType0):
            min_severity = self.min_severity.value
        else:
            min_severity = self.min_severity


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if label is not UNSET:
            field_dict["label"] = label
        if min_severity is not UNSET:
            field_dict["min_severity"] = min_severity

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))


        def _parse_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        label = _parse_label(d.pop("label", UNSET))


        def _parse_min_severity(data: object) -> None | PushSubscriptionUpdateMinSeverityType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                min_severity_type_0 = PushSubscriptionUpdateMinSeverityType0(data)



                return min_severity_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PushSubscriptionUpdateMinSeverityType0 | Unset, data)

        min_severity = _parse_min_severity(d.pop("min_severity", UNSET))


        push_subscription_update = cls(
            enabled=enabled,
            label=label,
            min_severity=min_severity,
        )


        push_subscription_update.additional_properties = d
        return push_subscription_update

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
