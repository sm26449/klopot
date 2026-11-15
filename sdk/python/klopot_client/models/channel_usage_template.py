from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.severity import Severity






T = TypeVar("T", bound="ChannelUsageTemplate")



@_attrs_define
class ChannelUsageTemplate:
    """ 
        Attributes:
            enabled (bool):
            severity_min (Severity):
            type_ (str):
     """

    enabled: bool
    severity_min: Severity
    type_: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        enabled = self.enabled

        severity_min = self.severity_min.value

        type_ = self.type_


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "enabled": enabled,
            "severity_min": severity_min,
            "type": type_,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        enabled = d.pop("enabled")

        severity_min = Severity(d.pop("severity_min"))




        type_ = d.pop("type")

        channel_usage_template = cls(
            enabled=enabled,
            severity_min=severity_min,
            type_=type_,
        )


        channel_usage_template.additional_properties = d
        return channel_usage_template

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
