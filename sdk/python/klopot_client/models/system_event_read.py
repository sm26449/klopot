from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="SystemEventRead")



@_attrs_define
class SystemEventRead:
    """ 
        Attributes:
            event (Any):
            id (Any):
            source_kind (Any):
            source_name (Any):
            ts (Any):
            detail (Any | Unset):
            source_id (Any | Unset):
     """

    event: Any
    id: Any
    source_kind: Any
    source_name: Any
    ts: Any
    detail: Any | Unset = UNSET
    source_id: Any | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        event = self.event

        id = self.id

        source_kind = self.source_kind

        source_name = self.source_name

        ts = self.ts

        detail = self.detail

        source_id = self.source_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "event": event,
            "id": id,
            "source_kind": source_kind,
            "source_name": source_name,
            "ts": ts,
        })
        if detail is not UNSET:
            field_dict["detail"] = detail
        if source_id is not UNSET:
            field_dict["source_id"] = source_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        event = d.pop("event")

        id = d.pop("id")

        source_kind = d.pop("source_kind")

        source_name = d.pop("source_name")

        ts = d.pop("ts")

        detail = d.pop("detail", UNSET)

        source_id = d.pop("source_id", UNSET)

        system_event_read = cls(
            event=event,
            id=id,
            source_kind=source_kind,
            source_name=source_name,
            ts=ts,
            detail=detail,
            source_id=source_id,
        )


        system_event_read.additional_properties = d
        return system_event_read

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
