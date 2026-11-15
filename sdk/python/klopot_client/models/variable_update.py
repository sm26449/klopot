from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.variable_source import VariableSource
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.variable_update_config_type_0 import VariableUpdateConfigType0





T = TypeVar("T", bound="VariableUpdate")



@_attrs_define
class VariableUpdate:
    """ 
        Attributes:
            config (None | Unset | VariableUpdateConfigType0):
            description (None | str | Unset):
            enabled (bool | None | Unset):
            input_id (int | None | Unset):
            source (None | Unset | VariableSource):
     """

    config: None | Unset | VariableUpdateConfigType0 = UNSET
    description: None | str | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    input_id: int | None | Unset = UNSET
    source: None | Unset | VariableSource = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.variable_update_config_type_0 import VariableUpdateConfigType0 # noqa: PLC0415
        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, VariableUpdateConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        input_id: int | None | Unset
        if isinstance(self.input_id, Unset):
            input_id = UNSET
        else:
            input_id = self.input_id

        source: None | str | Unset
        if isinstance(self.source, Unset):
            source = UNSET
        elif isinstance(self.source, VariableSource):
            source = self.source.value
        else:
            source = self.source


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if config is not UNSET:
            field_dict["config"] = config
        if description is not UNSET:
            field_dict["description"] = description
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if input_id is not UNSET:
            field_dict["input_id"] = input_id
        if source is not UNSET:
            field_dict["source"] = source

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.variable_update_config_type_0 import VariableUpdateConfigType0 # noqa: PLC0415
        d = dict(src_dict)
        def _parse_config(data: object) -> None | Unset | VariableUpdateConfigType0:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = VariableUpdateConfigType0.from_dict(data)



                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | VariableUpdateConfigType0, data)

        config = _parse_config(d.pop("config", UNSET))


        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))


        def _parse_input_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        input_id = _parse_input_id(d.pop("input_id", UNSET))


        def _parse_source(data: object) -> None | Unset | VariableSource:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                source_type_0 = VariableSource(data)



                return source_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | VariableSource, data)

        source = _parse_source(d.pop("source", UNSET))


        variable_update = cls(
            config=config,
            description=description,
            enabled=enabled,
            input_id=input_id,
            source=source,
        )


        variable_update.additional_properties = d
        return variable_update

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
