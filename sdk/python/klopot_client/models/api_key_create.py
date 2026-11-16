from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="ApiKeyCreate")



@_attrs_define
class ApiKeyCreate:
    """ 
        Attributes:
            name (str):
            allowed_cidrs (list[str] | Unset): Addresses the key may be used from: IPs or CIDRs (IPv4 and IPv6). Empty = any
                address. A request from elsewhere gets 403 and counts as a wrong key for that address.
            allowed_types (list[str] | Unset): Alert types the key may fire through POST /v1/fire: template types or
                patterns like backup_*. Empty = every type. Another type (or resolved_type) gets 403.
            enabled (bool | Unset):  Default: True.
            expires_at (datetime.datetime | None | Unset):
            rate_limit_per_min (int | None | Unset): Requests a minute the key may make; null = no limit. A quiet key may
                send this many at once, then one every 60/N seconds. Over it: 429 with Retry-After.
            scopes (list[str] | Unset):
     """

    name: str
    allowed_cidrs: list[str] | Unset = UNSET
    allowed_types: list[str] | Unset = UNSET
    enabled: bool | Unset = True
    expires_at: datetime.datetime | None | Unset = UNSET
    rate_limit_per_min: int | None | Unset = UNSET
    scopes: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        name = self.name

        allowed_cidrs: list[str] | Unset = UNSET
        if not isinstance(self.allowed_cidrs, Unset):
            allowed_cidrs = self.allowed_cidrs



        allowed_types: list[str] | Unset = UNSET
        if not isinstance(self.allowed_types, Unset):
            allowed_types = self.allowed_types



        enabled = self.enabled

        expires_at: None | str | Unset
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        elif isinstance(self.expires_at, datetime.datetime):
            expires_at = self.expires_at.isoformat()
        else:
            expires_at = self.expires_at

        rate_limit_per_min: int | None | Unset
        if isinstance(self.rate_limit_per_min, Unset):
            rate_limit_per_min = UNSET
        else:
            rate_limit_per_min = self.rate_limit_per_min

        scopes: list[str] | Unset = UNSET
        if not isinstance(self.scopes, Unset):
            scopes = self.scopes




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
        })
        if allowed_cidrs is not UNSET:
            field_dict["allowed_cidrs"] = allowed_cidrs
        if allowed_types is not UNSET:
            field_dict["allowed_types"] = allowed_types
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at
        if rate_limit_per_min is not UNSET:
            field_dict["rate_limit_per_min"] = rate_limit_per_min
        if scopes is not UNSET:
            field_dict["scopes"] = scopes

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        allowed_cidrs = cast(list[str], d.pop("allowed_cidrs", UNSET))


        allowed_types = cast(list[str], d.pop("allowed_types", UNSET))


        enabled = d.pop("enabled", UNSET)

        def _parse_expires_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                expires_at_type_0 = datetime.datetime.fromisoformat(data)



                return expires_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))


        def _parse_rate_limit_per_min(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        rate_limit_per_min = _parse_rate_limit_per_min(d.pop("rate_limit_per_min", UNSET))


        scopes = cast(list[str], d.pop("scopes", UNSET))


        api_key_create = cls(
            name=name,
            allowed_cidrs=allowed_cidrs,
            allowed_types=allowed_types,
            enabled=enabled,
            expires_at=expires_at,
            rate_limit_per_min=rate_limit_per_min,
            scopes=scopes,
        )


        api_key_create.additional_properties = d
        return api_key_create

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
