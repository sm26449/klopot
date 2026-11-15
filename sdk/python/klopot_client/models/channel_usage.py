from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.channel_usage_template import ChannelUsageTemplate





T = TypeVar("T", bound="ChannelUsage")



@_attrs_define
class ChannelUsage:
    """ Which templates route to a channel — blocks deletion when non-empty.

        Attributes:
            channel_id (int):
            channel_name (str):
            templates (list[ChannelUsageTemplate] | Unset):
     """

    channel_id: int
    channel_name: str
    templates: list[ChannelUsageTemplate] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.channel_usage_template import ChannelUsageTemplate # noqa: PLC0415
        channel_id = self.channel_id

        channel_name = self.channel_name

        templates: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.templates, Unset):
            templates = []
            for templates_item_data in self.templates:
                templates_item = templates_item_data.to_dict()
                templates.append(templates_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "channel_id": channel_id,
            "channel_name": channel_name,
        })
        if templates is not UNSET:
            field_dict["templates"] = templates

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.channel_usage_template import ChannelUsageTemplate # noqa: PLC0415
        d = dict(src_dict)
        channel_id = d.pop("channel_id")

        channel_name = d.pop("channel_name")

        _templates = d.pop("templates", UNSET)
        templates: list[ChannelUsageTemplate] | Unset = UNSET
        if _templates is not UNSET:
            templates = []
            for templates_item_data in _templates:
                templates_item = ChannelUsageTemplate.from_dict(templates_item_data)



                templates.append(templates_item)


        channel_usage = cls(
            channel_id=channel_id,
            channel_name=channel_name,
            templates=templates,
        )


        channel_usage.additional_properties = d
        return channel_usage

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
