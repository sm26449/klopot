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
  from ..models.input_update_config_type_0 import InputUpdateConfigType0





T = TypeVar("T", bound="InputUpdate")



@_attrs_define
class InputUpdate:
    """ 
        Attributes:
            config (InputUpdateConfigType0 | None | Unset):
            enabled (bool | None | Unset):
            kind (InputKind | None | Unset):
     """

    config: InputUpdateConfigType0 | None | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    kind: InputKind | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.input_update_config_type_0 import InputUpdateConfigType0 # noqa: PLC0415
        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, InputUpdateConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        kind: None | str | Unset
        if isinstance(self.kind, Unset):
            kind = UNSET
        elif isinstance(self.kind, InputKind):
            kind = self.kind.value
        else:
            kind = self.kind


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if config is not UNSET:
            field_dict["config"] = config
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if kind is not UNSET:
            field_dict["kind"] = kind

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.input_update_config_type_0 import InputUpdateConfigType0 # noqa: PLC0415
        d = dict(src_dict)
        def _parse_config(data: object) -> InputUpdateConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = InputUpdateConfigType0.from_dict(data)



                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(InputUpdateConfigType0 | None | Unset, data)

        config = _parse_config(d.pop("config", UNSET))


        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))


        def _parse_kind(data: object) -> InputKind | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                kind_type_0 = InputKind(data)



                return kind_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(InputKind | None | Unset, data)

        kind = _parse_kind(d.pop("kind", UNSET))


        input_update = cls(
            config=config,
            enabled=enabled,
            kind=kind,
        )


        input_update.additional_properties = d
        return input_update

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
