from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.var_state import VarState





T = TypeVar("T", bound="StateResponse")



@_attrs_define
class StateResponse:
    """ ``GET /v1/state`` body.

        Attributes:
            cache_size (int):
            variables (list[VarState]):
            last_mqtt_ts (float | None | Unset):
     """

    cache_size: int
    variables: list[VarState]
    last_mqtt_ts: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.var_state import VarState # noqa: PLC0415
        cache_size = self.cache_size

        variables = []
        for variables_item_data in self.variables:
            variables_item = variables_item_data.to_dict()
            variables.append(variables_item)



        last_mqtt_ts: float | None | Unset
        if isinstance(self.last_mqtt_ts, Unset):
            last_mqtt_ts = UNSET
        else:
            last_mqtt_ts = self.last_mqtt_ts


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "cache_size": cache_size,
            "variables": variables,
        })
        if last_mqtt_ts is not UNSET:
            field_dict["last_mqtt_ts"] = last_mqtt_ts

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.var_state import VarState # noqa: PLC0415
        d = dict(src_dict)
        cache_size = d.pop("cache_size")

        variables = []
        _variables = d.pop("variables")
        for variables_item_data in (_variables):
            variables_item = VarState.from_dict(variables_item_data)



            variables.append(variables_item)


        def _parse_last_mqtt_ts(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        last_mqtt_ts = _parse_last_mqtt_ts(d.pop("last_mqtt_ts", UNSET))


        state_response = cls(
            cache_size=cache_size,
            variables=variables,
            last_mqtt_ts=last_mqtt_ts,
        )


        state_response.additional_properties = d
        return state_response

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
