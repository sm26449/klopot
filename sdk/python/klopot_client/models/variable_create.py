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
  from ..models.variable_create_config import VariableCreateConfig





T = TypeVar("T", bound="VariableCreate")



@_attrs_define
class VariableCreate:
    """ 
        Attributes:
            name (str):
            source (VariableSource):
            config (VariableCreateConfig | Unset):
            description (None | str | Unset):
            enabled (bool | Unset):  Default: True.
            input_id (int | None | Unset):
     """

    name: str
    source: VariableSource
    config: VariableCreateConfig | Unset = UNSET
    description: None | str | Unset = UNSET
    enabled: bool | Unset = True
    input_id: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.variable_create_config import VariableCreateConfig # noqa: PLC0415
        name = self.name

        source = self.source.value

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        enabled = self.enabled

        input_id: int | None | Unset
        if isinstance(self.input_id, Unset):
            input_id = UNSET
        else:
            input_id = self.input_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
            "source": source,
        })
        if config is not UNSET:
            field_dict["config"] = config
        if description is not UNSET:
            field_dict["description"] = description
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if input_id is not UNSET:
            field_dict["input_id"] = input_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.variable_create_config import VariableCreateConfig # noqa: PLC0415
        d = dict(src_dict)
        name = d.pop("name")

        source = VariableSource(d.pop("source"))




        _config = d.pop("config", UNSET)
        config: VariableCreateConfig | Unset
        if isinstance(_config,  Unset):
            config = UNSET
        else:
            config = VariableCreateConfig.from_dict(_config)




        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        enabled = d.pop("enabled", UNSET)

        def _parse_input_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        input_id = _parse_input_id(d.pop("input_id", UNSET))


        variable_create = cls(
            name=name,
            source=source,
            config=config,
            description=description,
            enabled=enabled,
            input_id=input_id,
        )


        variable_create.additional_properties = d
        return variable_create

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
