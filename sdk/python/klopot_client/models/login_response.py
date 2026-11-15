from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.user_read import UserRead





T = TypeVar("T", bound="LoginResponse")



@_attrs_define
class LoginResponse:
    """ 
        Attributes:
            csrf_token (str):
            user (UserRead):
     """

    csrf_token: str
    user: UserRead
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.user_read import UserRead # noqa: PLC0415
        csrf_token = self.csrf_token

        user = self.user.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "csrf_token": csrf_token,
            "user": user,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user_read import UserRead # noqa: PLC0415
        d = dict(src_dict)
        csrf_token = d.pop("csrf_token")

        user = UserRead.from_dict(d.pop("user"))




        login_response = cls(
            csrf_token=csrf_token,
            user=user,
        )


        login_response.additional_properties = d
        return login_response

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
