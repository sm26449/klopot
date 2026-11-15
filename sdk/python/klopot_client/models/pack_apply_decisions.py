from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.pack_apply_decisions_additional_property import PackApplyDecisionsAdditionalProperty






T = TypeVar("T", bound="PackApplyDecisions")



@_attrs_define
class PackApplyDecisions:
    """ Per item "<section>:<key>": overwrite, skip or copy (as /v1/config/import/apply).

     """

    additional_properties: dict[str, PackApplyDecisionsAdditionalProperty] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        
        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.value


        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        pack_apply_decisions = cls(
        )


        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = PackApplyDecisionsAdditionalProperty(prop_dict)



            additional_properties[prop_name] = additional_property

        pack_apply_decisions.additional_properties = additional_properties
        return pack_apply_decisions

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> PackApplyDecisionsAdditionalProperty:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: PackApplyDecisionsAdditionalProperty) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
