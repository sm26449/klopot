from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.health_status_status import HealthStatusStatus
from ..types import UNSET, Unset






T = TypeVar("T", bound="HealthStatus")



@_attrs_define
class HealthStatus:
    """ ``GET /v1/health`` for a caller without ``read``: the overall status
    only. The components name hosts, inputs and error texts, and the version
    tells an attacker what to try (public-exposure review F7, F13).

        Attributes:
            status (HealthStatusStatus):
            service (str | Unset):  Default: 'alertd'.
     """

    status: HealthStatusStatus
    service: str | Unset = 'alertd'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        status = self.status.value

        service = self.service


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "status": status,
        })
        if service is not UNSET:
            field_dict["service"] = service

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        status = HealthStatusStatus(d.pop("status"))




        service = d.pop("service", UNSET)

        health_status = cls(
            status=status,
            service=service,
        )


        health_status.additional_properties = d
        return health_status

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
