from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="SessionRead")



@_attrs_define
class SessionRead:
    """ 
        Attributes:
            created_at (None | str):
            expires_at (None | str):
            id (int):
            last_seen_at (None | str):
            current (bool | Unset):  Default: False.
            ip (None | str | Unset):
            user_agent (None | str | Unset):
     """

    created_at: None | str
    expires_at: None | str
    id: int
    last_seen_at: None | str
    current: bool | Unset = False
    ip: None | str | Unset = UNSET
    user_agent: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at: None | str
        created_at = self.created_at

        expires_at: None | str
        expires_at = self.expires_at

        id = self.id

        last_seen_at: None | str
        last_seen_at = self.last_seen_at

        current = self.current

        ip: None | str | Unset
        if isinstance(self.ip, Unset):
            ip = UNSET
        else:
            ip = self.ip

        user_agent: None | str | Unset
        if isinstance(self.user_agent, Unset):
            user_agent = UNSET
        else:
            user_agent = self.user_agent


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "expires_at": expires_at,
            "id": id,
            "last_seen_at": last_seen_at,
        })
        if current is not UNSET:
            field_dict["current"] = current
        if ip is not UNSET:
            field_dict["ip"] = ip
        if user_agent is not UNSET:
            field_dict["user_agent"] = user_agent

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        def _parse_expires_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        expires_at = _parse_expires_at(d.pop("expires_at"))


        id = d.pop("id")

        def _parse_last_seen_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        last_seen_at = _parse_last_seen_at(d.pop("last_seen_at"))


        current = d.pop("current", UNSET)

        def _parse_ip(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ip = _parse_ip(d.pop("ip", UNSET))


        def _parse_user_agent(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_agent = _parse_user_agent(d.pop("user_agent", UNSET))


        session_read = cls(
            created_at=created_at,
            expires_at=expires_at,
            id=id,
            last_seen_at=last_seen_at,
            current=current,
            ip=ip,
            user_agent=user_agent,
        )


        session_read.additional_properties = d
        return session_read

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
