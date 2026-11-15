from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.ignored_row import IgnoredRow
  from ..models.source_row import SourceRow





T = TypeVar("T", bound="SourcesResponse")



@_attrs_define
class SourcesResponse:
    """ 
        Attributes:
            hours (int):
            ignored (list[IgnoredRow]):
            sources (list[SourceRow]):
     """

    hours: int
    ignored: list[IgnoredRow]
    sources: list[SourceRow]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.ignored_row import IgnoredRow # noqa: PLC0415
        from ..models.source_row import SourceRow # noqa: PLC0415
        hours = self.hours

        ignored = []
        for ignored_item_data in self.ignored:
            ignored_item = ignored_item_data.to_dict()
            ignored.append(ignored_item)



        sources = []
        for sources_item_data in self.sources:
            sources_item = sources_item_data.to_dict()
            sources.append(sources_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "hours": hours,
            "ignored": ignored,
            "sources": sources,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ignored_row import IgnoredRow # noqa: PLC0415
        from ..models.source_row import SourceRow # noqa: PLC0415
        d = dict(src_dict)
        hours = d.pop("hours")

        ignored = []
        _ignored = d.pop("ignored")
        for ignored_item_data in (_ignored):
            ignored_item = IgnoredRow.from_dict(ignored_item_data)



            ignored.append(ignored_item)


        sources = []
        _sources = d.pop("sources")
        for sources_item_data in (_sources):
            sources_item = SourceRow.from_dict(sources_item_data)



            sources.append(sources_item)


        sources_response = cls(
            hours=hours,
            ignored=ignored,
            sources=sources,
        )


        sources_response.additional_properties = d
        return sources_response

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
