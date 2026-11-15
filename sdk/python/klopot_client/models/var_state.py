from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="VarState")



@_attrs_define
class VarState:
    """ One entry in ``GET /v1/state``.

        Attributes:
            age_sec (float):
            name (str):
            value (Any):
            wall_ts (float):
            source_kind (str | Unset):  Default: 'unknown'.
            source_topic (None | str | Unset):
     """

    age_sec: float
    name: str
    value: Any
    wall_ts: float
    source_kind: str | Unset = 'unknown'
    source_topic: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        age_sec = self.age_sec

        name = self.name

        value = self.value

        wall_ts = self.wall_ts

        source_kind = self.source_kind

        source_topic: None | str | Unset
        if isinstance(self.source_topic, Unset):
            source_topic = UNSET
        else:
            source_topic = self.source_topic


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "age_sec": age_sec,
            "name": name,
            "value": value,
            "wall_ts": wall_ts,
        })
        if source_kind is not UNSET:
            field_dict["source_kind"] = source_kind
        if source_topic is not UNSET:
            field_dict["source_topic"] = source_topic

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        age_sec = d.pop("age_sec")

        name = d.pop("name")

        value = d.pop("value")

        wall_ts = d.pop("wall_ts")

        source_kind = d.pop("source_kind", UNSET)

        def _parse_source_topic(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source_topic = _parse_source_topic(d.pop("source_topic", UNSET))


        var_state = cls(
            age_sec=age_sec,
            name=name,
            value=value,
            wall_ts=wall_ts,
            source_kind=source_kind,
            source_topic=source_topic,
        )


        var_state.additional_properties = d
        return var_state

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
