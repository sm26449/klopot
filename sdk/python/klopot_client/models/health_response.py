from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.health_response_status import HealthResponseStatus
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.health_response_components import HealthResponseComponents





T = TypeVar("T", bound="HealthResponse")



@_attrs_define
class HealthResponse:
    """ ``GET /v1/health`` for a ``read`` caller (an API key with ``read``, or
    a signed-in user): the status plus the component map.

    HTTP status is always 200 — clients inspect ``status`` field.
    Degraded components don't trigger Kubernetes restart loops.

        Attributes:
            components (HealthResponseComponents):
            status (HealthResponseStatus):
            docs_enabled (bool | Unset):  Default: True.
            service (str | Unset):  Default: 'alertd'.
            version (str | Unset):  Default: '1.3.0-rc.9'.
     """

    components: HealthResponseComponents
    status: HealthResponseStatus
    docs_enabled: bool | Unset = True
    service: str | Unset = 'alertd'
    version: str | Unset = '1.3.0-rc.9'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.health_response_components import HealthResponseComponents # noqa: PLC0415
        components = self.components.to_dict()

        status = self.status.value

        docs_enabled = self.docs_enabled

        service = self.service

        version = self.version


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "components": components,
            "status": status,
        })
        if docs_enabled is not UNSET:
            field_dict["docs_enabled"] = docs_enabled
        if service is not UNSET:
            field_dict["service"] = service
        if version is not UNSET:
            field_dict["version"] = version

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.health_response_components import HealthResponseComponents # noqa: PLC0415
        d = dict(src_dict)
        components = HealthResponseComponents.from_dict(d.pop("components"))




        status = HealthResponseStatus(d.pop("status"))




        docs_enabled = d.pop("docs_enabled", UNSET)

        service = d.pop("service", UNSET)

        version = d.pop("version", UNSET)

        health_response = cls(
            components=components,
            status=status,
            docs_enabled=docs_enabled,
            service=service,
            version=version,
        )


        health_response.additional_properties = d
        return health_response

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
