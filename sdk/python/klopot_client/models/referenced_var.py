from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ReferencedVar")



@_attrs_define
class ReferencedVar:
    """ 
        Attributes:
            name (str):
            age_sec (float | None | Unset):
            is_stale (bool | Unset):  Default: False.
            live_value (Any | Unset):
            present (bool | Unset):  Default: True.
     """

    name: str
    age_sec: float | None | Unset = UNSET
    is_stale: bool | Unset = False
    live_value: Any | Unset = UNSET
    present: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        name = self.name

        age_sec: float | None | Unset
        if isinstance(self.age_sec, Unset):
            age_sec = UNSET
        else:
            age_sec = self.age_sec

        is_stale = self.is_stale

        live_value = self.live_value

        present = self.present


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
        })
        if age_sec is not UNSET:
            field_dict["age_sec"] = age_sec
        if is_stale is not UNSET:
            field_dict["is_stale"] = is_stale
        if live_value is not UNSET:
            field_dict["live_value"] = live_value
        if present is not UNSET:
            field_dict["present"] = present

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        def _parse_age_sec(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        age_sec = _parse_age_sec(d.pop("age_sec", UNSET))


        is_stale = d.pop("is_stale", UNSET)

        live_value = d.pop("live_value", UNSET)

        present = d.pop("present", UNSET)

        referenced_var = cls(
            name=name,
            age_sec=age_sec,
            is_stale=is_stale,
            live_value=live_value,
            present=present,
        )


        referenced_var.additional_properties = d
        return referenced_var

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
