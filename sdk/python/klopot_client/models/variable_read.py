from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.variable_read_value_state import VariableReadValueState
from ..models.variable_source import VariableSource
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.variable_read_config import VariableReadConfig





T = TypeVar("T", bound="VariableRead")



@_attrs_define
class VariableRead:
    """ 
        Attributes:
            created_at (None | str):
            id (int):
            name (str):
            source (VariableSource):
            updated_at (None | str):
            value_state (VariableReadValueState): ``missing``: no value received since start-up; ``stale``: older
                than its window; ``fresh`` otherwise.
            age_sec (float | None | Unset):
            config (VariableReadConfig | Unset):
            description (None | str | Unset):
            enabled (bool | Unset):  Default: True.
            input_id (int | None | Unset):
            is_stale (bool | None | Unset):
            last_value (Any | None | Unset):
            last_value_at (None | str | Unset):
            used_by_rules (list[str] | Unset):
            used_by_variables (list[str] | Unset):
     """

    created_at: None | str
    id: int
    name: str
    source: VariableSource
    updated_at: None | str
    value_state: VariableReadValueState
    age_sec: float | None | Unset = UNSET
    config: VariableReadConfig | Unset = UNSET
    description: None | str | Unset = UNSET
    enabled: bool | Unset = True
    input_id: int | None | Unset = UNSET
    is_stale: bool | None | Unset = UNSET
    last_value: Any | None | Unset = UNSET
    last_value_at: None | str | Unset = UNSET
    used_by_rules: list[str] | Unset = UNSET
    used_by_variables: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.variable_read_config import VariableReadConfig # noqa: PLC0415
        created_at: None | str
        created_at = self.created_at

        id = self.id

        name = self.name

        source = self.source.value

        updated_at: None | str
        updated_at = self.updated_at

        value_state = self.value_state.value

        age_sec: float | None | Unset
        if isinstance(self.age_sec, Unset):
            age_sec = UNSET
        else:
            age_sec = self.age_sec

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

        is_stale: bool | None | Unset
        if isinstance(self.is_stale, Unset):
            is_stale = UNSET
        else:
            is_stale = self.is_stale

        last_value: Any | None | Unset
        if isinstance(self.last_value, Unset):
            last_value = UNSET
        else:
            last_value = self.last_value

        last_value_at: None | str | Unset
        if isinstance(self.last_value_at, Unset):
            last_value_at = UNSET
        else:
            last_value_at = self.last_value_at

        used_by_rules: list[str] | Unset = UNSET
        if not isinstance(self.used_by_rules, Unset):
            used_by_rules = self.used_by_rules



        used_by_variables: list[str] | Unset = UNSET
        if not isinstance(self.used_by_variables, Unset):
            used_by_variables = self.used_by_variables




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "id": id,
            "name": name,
            "source": source,
            "updated_at": updated_at,
            "value_state": value_state,
        })
        if age_sec is not UNSET:
            field_dict["age_sec"] = age_sec
        if config is not UNSET:
            field_dict["config"] = config
        if description is not UNSET:
            field_dict["description"] = description
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if input_id is not UNSET:
            field_dict["input_id"] = input_id
        if is_stale is not UNSET:
            field_dict["is_stale"] = is_stale
        if last_value is not UNSET:
            field_dict["last_value"] = last_value
        if last_value_at is not UNSET:
            field_dict["last_value_at"] = last_value_at
        if used_by_rules is not UNSET:
            field_dict["used_by_rules"] = used_by_rules
        if used_by_variables is not UNSET:
            field_dict["used_by_variables"] = used_by_variables

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.variable_read_config import VariableReadConfig # noqa: PLC0415
        d = dict(src_dict)
        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        id = d.pop("id")

        name = d.pop("name")

        source = VariableSource(d.pop("source"))




        def _parse_updated_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))


        value_state = VariableReadValueState(d.pop("value_state"))




        def _parse_age_sec(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        age_sec = _parse_age_sec(d.pop("age_sec", UNSET))


        _config = d.pop("config", UNSET)
        config: VariableReadConfig | Unset
        if isinstance(_config,  Unset):
            config = UNSET
        else:
            config = VariableReadConfig.from_dict(_config)




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


        def _parse_is_stale(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        is_stale = _parse_is_stale(d.pop("is_stale", UNSET))


        def _parse_last_value(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        last_value = _parse_last_value(d.pop("last_value", UNSET))


        def _parse_last_value_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_value_at = _parse_last_value_at(d.pop("last_value_at", UNSET))


        used_by_rules = cast(list[str], d.pop("used_by_rules", UNSET))


        used_by_variables = cast(list[str], d.pop("used_by_variables", UNSET))


        variable_read = cls(
            created_at=created_at,
            id=id,
            name=name,
            source=source,
            updated_at=updated_at,
            value_state=value_state,
            age_sec=age_sec,
            config=config,
            description=description,
            enabled=enabled,
            input_id=input_id,
            is_stale=is_stale,
            last_value=last_value,
            last_value_at=last_value_at,
            used_by_rules=used_by_rules,
            used_by_variables=used_by_variables,
        )


        variable_read.additional_properties = d
        return variable_read

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
