from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.api_key_read import ApiKeyRead





T = TypeVar("T", bound="PageApiKeyRead")



@_attrs_define
class PageApiKeyRead:
    """ 
        Attributes:
            items (list[ApiKeyRead]):
            limit (int):
            offset (int):
            total (int):
     """

    items: list[ApiKeyRead]
    limit: int
    offset: int
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.api_key_read import ApiKeyRead # noqa: PLC0415
        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)



        limit = self.limit

        offset = self.offset

        total = self.total


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "items": items,
            "limit": limit,
            "offset": offset,
            "total": total,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.api_key_read import ApiKeyRead # noqa: PLC0415
        d = dict(src_dict)
        items = []
        _items = d.pop("items")
        for items_item_data in (_items):
            items_item = ApiKeyRead.from_dict(items_item_data)



            items.append(items_item)


        limit = d.pop("limit")

        offset = d.pop("offset")

        total = d.pop("total")

        page_api_key_read = cls(
            items=items,
            limit=limit,
            offset=offset,
            total=total,
        )


        page_api_key_read.additional_properties = d
        return page_api_key_read

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
