from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ApiKeyRead")



@_attrs_define
class ApiKeyRead:
    """ Public read shape — never includes the plaintext key.

        Attributes:
            created_at (None | str):
            enabled (bool):
            id (int):
            key_prefix (str):
            name (str):
            scopes (list[str]):
            expires_at (None | str | Unset):
            last_used_at (None | str | Unset):
            last_used_ip (None | str | Unset):
            rotated_from_id (int | None | Unset):
     """

    created_at: None | str
    enabled: bool
    id: int
    key_prefix: str
    name: str
    scopes: list[str]
    expires_at: None | str | Unset = UNSET
    last_used_at: None | str | Unset = UNSET
    last_used_ip: None | str | Unset = UNSET
    rotated_from_id: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at: None | str
        created_at = self.created_at

        enabled = self.enabled

        id = self.id

        key_prefix = self.key_prefix

        name = self.name

        scopes = self.scopes



        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        else:
            expires_at = self.expires_at

        last_used_at: None | str | Unset
        if isinstance(self.last_used_at, Unset):
            last_used_at = UNSET
        else:
            last_used_at = self.last_used_at

        last_used_ip: None | str | Unset
        if isinstance(self.last_used_ip, Unset):
            last_used_ip = UNSET
        else:
            last_used_ip = self.last_used_ip

        rotated_from_id: int | None | Unset
        if isinstance(self.rotated_from_id, Unset):
            rotated_from_id = UNSET
        else:
            rotated_from_id = self.rotated_from_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "enabled": enabled,
            "id": id,
            "key_prefix": key_prefix,
            "name": name,
            "scopes": scopes,
        })
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at
        if last_used_at is not UNSET:
            field_dict["last_used_at"] = last_used_at
        if last_used_ip is not UNSET:
            field_dict["last_used_ip"] = last_used_ip
        if rotated_from_id is not UNSET:
            field_dict["rotated_from_id"] = rotated_from_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        enabled = d.pop("enabled")

        id = d.pop("id")

        key_prefix = d.pop("key_prefix")

        name = d.pop("name")

        scopes = cast(list[str], d.pop("scopes"))


        def _parse_expires_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))


        def _parse_last_used_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_used_at = _parse_last_used_at(d.pop("last_used_at", UNSET))


        def _parse_last_used_ip(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_used_ip = _parse_last_used_ip(d.pop("last_used_ip", UNSET))


        def _parse_rotated_from_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        rotated_from_id = _parse_rotated_from_id(d.pop("rotated_from_id", UNSET))


        api_key_read = cls(
            created_at=created_at,
            enabled=enabled,
            id=id,
            key_prefix=key_prefix,
            name=name,
            scopes=scopes,
            expires_at=expires_at,
            last_used_at=last_used_at,
            last_used_ip=last_used_ip,
            rotated_from_id=rotated_from_id,
        )


        api_key_read.additional_properties = d
        return api_key_read

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
