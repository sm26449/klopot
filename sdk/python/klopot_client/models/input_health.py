from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.input_kind import InputKind
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="InputHealth")



@_attrs_define
class InputHealth:
    """ Snapshot returned by ``GET /v1/inputs/{id}/health``.

        Attributes:
            connected (bool):
            kind (InputKind):
            name (str):
            error (None | str | Unset):
            last_msg_ts (float | None | Unset):
            msg_count (int | Unset):  Default: 0.
     """

    connected: bool
    kind: InputKind
    name: str
    error: None | str | Unset = UNSET
    last_msg_ts: float | None | Unset = UNSET
    msg_count: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        connected = self.connected

        kind = self.kind.value

        name = self.name

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        last_msg_ts: float | None | Unset
        if isinstance(self.last_msg_ts, Unset):
            last_msg_ts = UNSET
        else:
            last_msg_ts = self.last_msg_ts

        msg_count = self.msg_count


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "connected": connected,
            "kind": kind,
            "name": name,
        })
        if error is not UNSET:
            field_dict["error"] = error
        if last_msg_ts is not UNSET:
            field_dict["last_msg_ts"] = last_msg_ts
        if msg_count is not UNSET:
            field_dict["msg_count"] = msg_count

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        connected = d.pop("connected")

        kind = InputKind(d.pop("kind"))




        name = d.pop("name")

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))


        def _parse_last_msg_ts(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        last_msg_ts = _parse_last_msg_ts(d.pop("last_msg_ts", UNSET))


        msg_count = d.pop("msg_count", UNSET)

        input_health = cls(
            connected=connected,
            kind=kind,
            name=name,
            error=error,
            last_msg_ts=last_msg_ts,
            msg_count=msg_count,
        )


        input_health.additional_properties = d
        return input_health

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
