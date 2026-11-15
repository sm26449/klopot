from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="UserRead")



@_attrs_define
class UserRead:
    """ 
        Attributes:
            must_change_password (bool):
            role (str):
            username (str):
            last_login_at (None | str | Unset):
            password_changed_at (None | str | Unset):
     """

    must_change_password: bool
    role: str
    username: str
    last_login_at: None | str | Unset = UNSET
    password_changed_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        must_change_password = self.must_change_password

        role = self.role

        username = self.username

        last_login_at: None | str | Unset
        if isinstance(self.last_login_at, Unset):
            last_login_at = UNSET
        else:
            last_login_at = self.last_login_at

        password_changed_at: None | str | Unset
        if isinstance(self.password_changed_at, Unset):
            password_changed_at = UNSET
        else:
            password_changed_at = self.password_changed_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "must_change_password": must_change_password,
            "role": role,
            "username": username,
        })
        if last_login_at is not UNSET:
            field_dict["last_login_at"] = last_login_at
        if password_changed_at is not UNSET:
            field_dict["password_changed_at"] = password_changed_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        must_change_password = d.pop("must_change_password")

        role = d.pop("role")

        username = d.pop("username")

        def _parse_last_login_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_login_at = _parse_last_login_at(d.pop("last_login_at", UNSET))


        def _parse_password_changed_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        password_changed_at = _parse_password_changed_at(d.pop("password_changed_at", UNSET))


        user_read = cls(
            must_change_password=must_change_password,
            role=role,
            username=username,
            last_login_at=last_login_at,
            password_changed_at=password_changed_at,
        )


        user_read.additional_properties = d
        return user_read

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
