from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.component_health_status import ComponentHealthStatus
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.component_health_params import ComponentHealthParams





T = TypeVar("T", bound="ComponentHealth")



@_attrs_define
class ComponentHealth:
    """ Per-component health snapshot.

        Attributes:
            status (ComponentHealthStatus):
            code (None | str | Unset):
            detail (None | str | Unset):
            params (ComponentHealthParams | Unset):
     """

    status: ComponentHealthStatus
    code: None | str | Unset = UNSET
    detail: None | str | Unset = UNSET
    params: ComponentHealthParams | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.component_health_params import ComponentHealthParams # noqa: PLC0415
        status = self.status.value

        code: None | str | Unset
        if isinstance(self.code, Unset):
            code = UNSET
        else:
            code = self.code

        detail: None | str | Unset
        if isinstance(self.detail, Unset):
            detail = UNSET
        else:
            detail = self.detail

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "status": status,
        })
        if code is not UNSET:
            field_dict["code"] = code
        if detail is not UNSET:
            field_dict["detail"] = detail
        if params is not UNSET:
            field_dict["params"] = params

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.component_health_params import ComponentHealthParams # noqa: PLC0415
        d = dict(src_dict)
        status = ComponentHealthStatus(d.pop("status"))




        def _parse_code(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        code = _parse_code(d.pop("code", UNSET))


        def _parse_detail(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        detail = _parse_detail(d.pop("detail", UNSET))


        _params = d.pop("params", UNSET)
        params: ComponentHealthParams | Unset
        if isinstance(_params,  Unset):
            params = UNSET
        else:
            params = ComponentHealthParams.from_dict(_params)




        component_health = cls(
            status=status,
            code=code,
            detail=detail,
            params=params,
        )


        component_health.additional_properties = d
        return component_health

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
