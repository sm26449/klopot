from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.input_kind import InputKind
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.input_create_config import InputCreateConfig





T = TypeVar("T", bound="InputCreate")



@_attrs_define
class InputCreate:
    """ 
        Attributes:
            kind (InputKind):
            name (str):
            config (InputCreateConfig | Unset):
            enabled (bool | Unset):  Default: True.
     """

    kind: InputKind
    name: str
    config: InputCreateConfig | Unset = UNSET
    enabled: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.input_create_config import InputCreateConfig # noqa: PLC0415
        kind = self.kind.value

        name = self.name

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        enabled = self.enabled


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "kind": kind,
            "name": name,
        })
        if config is not UNSET:
            field_dict["config"] = config
        if enabled is not UNSET:
            field_dict["enabled"] = enabled

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.input_create_config import InputCreateConfig # noqa: PLC0415
        d = dict(src_dict)
        kind = InputKind(d.pop("kind"))




        name = d.pop("name")

        _config = d.pop("config", UNSET)
        config: InputCreateConfig | Unset
        if isinstance(_config,  Unset):
            config = UNSET
        else:
            config = InputCreateConfig.from_dict(_config)




        enabled = d.pop("enabled", UNSET)

        input_create = cls(
            kind=kind,
            name=name,
            config=config,
            enabled=enabled,
        )


        input_create.additional_properties = d
        return input_create

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
