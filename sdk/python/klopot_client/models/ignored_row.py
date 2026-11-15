from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast






T = TypeVar("T", bound="IgnoredRow")



@_attrs_define
class IgnoredRow:
    """ Requests an `ignore` rule kept out of the log — counted only.

        Attributes:
            hits (int):
            last_hit_at (None | str):
            last_ip (None | str):
            name (str):
            pattern (str):
            rule_id (int):
     """

    hits: int
    last_hit_at: None | str
    last_ip: None | str
    name: str
    pattern: str
    rule_id: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        hits = self.hits

        last_hit_at: None | str
        last_hit_at = self.last_hit_at

        last_ip: None | str
        last_ip = self.last_ip

        name = self.name

        pattern = self.pattern

        rule_id = self.rule_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "hits": hits,
            "last_hit_at": last_hit_at,
            "last_ip": last_ip,
            "name": name,
            "pattern": pattern,
            "rule_id": rule_id,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        hits = d.pop("hits")

        def _parse_last_hit_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        last_hit_at = _parse_last_hit_at(d.pop("last_hit_at"))


        def _parse_last_ip(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        last_ip = _parse_last_ip(d.pop("last_ip"))


        name = d.pop("name")

        pattern = d.pop("pattern")

        rule_id = d.pop("rule_id")

        ignored_row = cls(
            hits=hits,
            last_hit_at=last_hit_at,
            last_ip=last_ip,
            name=name,
            pattern=pattern,
            rule_id=rule_id,
        )


        ignored_row.additional_properties = d
        return ignored_row

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
