from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.session_read import SessionRead
  from ..models.user_read import UserRead





T = TypeVar("T", bound="MeResponse")



@_attrs_define
class MeResponse:
    """ 
        Attributes:
            scopes (list[str]):
            session (SessionRead):
            user (UserRead):
            client_ip (None | str | Unset):
     """

    scopes: list[str]
    session: SessionRead
    user: UserRead
    client_ip: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.session_read import SessionRead # noqa: PLC0415
        from ..models.user_read import UserRead # noqa: PLC0415
        scopes = self.scopes



        session = self.session.to_dict()

        user = self.user.to_dict()

        client_ip: None | str | Unset
        if isinstance(self.client_ip, Unset):
            client_ip = UNSET
        else:
            client_ip = self.client_ip


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "scopes": scopes,
            "session": session,
            "user": user,
        })
        if client_ip is not UNSET:
            field_dict["client_ip"] = client_ip

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.session_read import SessionRead # noqa: PLC0415
        from ..models.user_read import UserRead # noqa: PLC0415
        d = dict(src_dict)
        scopes = cast(list[str], d.pop("scopes"))


        session = SessionRead.from_dict(d.pop("session"))




        user = UserRead.from_dict(d.pop("user"))




        def _parse_client_ip(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        client_ip = _parse_client_ip(d.pop("client_ip", UNSET))


        me_response = cls(
            scopes=scopes,
            session=session,
            user=user,
            client_ip=client_ip,
        )


        me_response.additional_properties = d
        return me_response

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
