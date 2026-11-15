from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.source_row_by_class import SourceRowByClass





T = TypeVar("T", bound="SourceRow")



@_attrs_define
class SourceRow:
    """ Requests grouped by who sent them and where.

        Attributes:
            actor_name (None | str):
            by_class (SourceRowByClass): Counts per status class, e.g. {"2xx": 120, "4xx": 3}.
            client_ip (None | str):
            last_seen (None | str):
            method (str):
            route (str):
            total (int):
     """

    actor_name: None | str
    by_class: SourceRowByClass
    client_ip: None | str
    last_seen: None | str
    method: str
    route: str
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.source_row_by_class import SourceRowByClass # noqa: PLC0415
        actor_name: None | str
        actor_name = self.actor_name

        by_class = self.by_class.to_dict()

        client_ip: None | str
        client_ip = self.client_ip

        last_seen: None | str
        last_seen = self.last_seen

        method = self.method

        route = self.route

        total = self.total


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "actor_name": actor_name,
            "by_class": by_class,
            "client_ip": client_ip,
            "last_seen": last_seen,
            "method": method,
            "route": route,
            "total": total,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.source_row_by_class import SourceRowByClass # noqa: PLC0415
        d = dict(src_dict)
        def _parse_actor_name(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        actor_name = _parse_actor_name(d.pop("actor_name"))


        by_class = SourceRowByClass.from_dict(d.pop("by_class"))




        def _parse_client_ip(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        client_ip = _parse_client_ip(d.pop("client_ip"))


        def _parse_last_seen(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        last_seen = _parse_last_seen(d.pop("last_seen"))


        method = d.pop("method")

        route = d.pop("route")

        total = d.pop("total")

        source_row = cls(
            actor_name=actor_name,
            by_class=by_class,
            client_ip=client_ip,
            last_seen=last_seen,
            method=method,
            route=route,
            total=total,
        )


        source_row.additional_properties = d
        return source_row

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
