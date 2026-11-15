from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.pack_source_params import PackSourceParams





T = TypeVar("T", bound="PackSource")



@_attrs_define
class PackSource:
    """ 
        Attributes:
            pack_id (None | str | Unset): A catalog pack (GET /v1/packs).
            params (PackSourceParams | Unset): Parameter values by name; omitted ones take their default.
            yaml (None | str | Unset): Your own pack, as YAML text.
     """

    pack_id: None | str | Unset = UNSET
    params: PackSourceParams | Unset = UNSET
    yaml: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pack_source_params import PackSourceParams # noqa: PLC0415
        pack_id: None | str | Unset
        if isinstance(self.pack_id, Unset):
            pack_id = UNSET
        else:
            pack_id = self.pack_id

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        yaml: None | str | Unset
        if isinstance(self.yaml, Unset):
            yaml = UNSET
        else:
            yaml = self.yaml


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if pack_id is not UNSET:
            field_dict["pack_id"] = pack_id
        if params is not UNSET:
            field_dict["params"] = params
        if yaml is not UNSET:
            field_dict["yaml"] = yaml

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pack_source_params import PackSourceParams # noqa: PLC0415
        d = dict(src_dict)
        def _parse_pack_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pack_id = _parse_pack_id(d.pop("pack_id", UNSET))


        _params = d.pop("params", UNSET)
        params: PackSourceParams | Unset
        if isinstance(_params,  Unset):
            params = UNSET
        else:
            params = PackSourceParams.from_dict(_params)




        def _parse_yaml(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        yaml = _parse_yaml(d.pop("yaml", UNSET))


        pack_source = cls(
            pack_id=pack_id,
            params=params,
            yaml=yaml,
        )


        pack_source.additional_properties = d
        return pack_source

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
