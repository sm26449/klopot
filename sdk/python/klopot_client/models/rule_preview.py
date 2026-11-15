from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.api_request_read import ApiRequestRead





T = TypeVar("T", bound="RulePreview")



@_attrs_define
class RulePreview:
    """ 
        Attributes:
            checked (int):
            examples (list[ApiRequestRead]):
            matched (int):
            window_hours (int):
     """

    checked: int
    examples: list[ApiRequestRead]
    matched: int
    window_hours: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.api_request_read import ApiRequestRead # noqa: PLC0415
        checked = self.checked

        examples = []
        for examples_item_data in self.examples:
            examples_item = examples_item_data.to_dict()
            examples.append(examples_item)



        matched = self.matched

        window_hours = self.window_hours


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "checked": checked,
            "examples": examples,
            "matched": matched,
            "window_hours": window_hours,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.api_request_read import ApiRequestRead # noqa: PLC0415
        d = dict(src_dict)
        checked = d.pop("checked")

        examples = []
        _examples = d.pop("examples")
        for examples_item_data in (_examples):
            examples_item = ApiRequestRead.from_dict(examples_item_data)



            examples.append(examples_item)


        matched = d.pop("matched")

        window_hours = d.pop("window_hours")

        rule_preview = cls(
            checked=checked,
            examples=examples,
            matched=matched,
            window_hours=window_hours,
        )


        rule_preview.additional_properties = d
        return rule_preview

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
