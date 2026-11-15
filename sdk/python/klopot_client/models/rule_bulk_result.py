from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RuleBulkResult")



@_attrs_define
class RuleBulkResult:
    """ 
        Attributes:
            not_found (list[int] | Unset):
            unchanged (list[int] | Unset):
            updated (list[int] | Unset):
     """

    not_found: list[int] | Unset = UNSET
    unchanged: list[int] | Unset = UNSET
    updated: list[int] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        not_found: list[int] | Unset = UNSET
        if not isinstance(self.not_found, Unset):
            not_found = self.not_found



        unchanged: list[int] | Unset = UNSET
        if not isinstance(self.unchanged, Unset):
            unchanged = self.unchanged



        updated: list[int] | Unset = UNSET
        if not isinstance(self.updated, Unset):
            updated = self.updated




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if not_found is not UNSET:
            field_dict["not_found"] = not_found
        if unchanged is not UNSET:
            field_dict["unchanged"] = unchanged
        if updated is not UNSET:
            field_dict["updated"] = updated

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        not_found = cast(list[int], d.pop("not_found", UNSET))


        unchanged = cast(list[int], d.pop("unchanged", UNSET))


        updated = cast(list[int], d.pop("updated", UNSET))


        rule_bulk_result = cls(
            not_found=not_found,
            unchanged=unchanged,
            updated=updated,
        )


        rule_bulk_result.additional_properties = d
        return rule_bulk_result

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
