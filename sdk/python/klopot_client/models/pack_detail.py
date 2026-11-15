from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.pack_detail_counts import PackDetailCounts
  from ..models.pack_detail_description_type_1 import PackDetailDescriptionType1
  from ..models.pack_detail_name_type_1 import PackDetailNameType1
  from ..models.pack_parameter_out import PackParameterOut





T = TypeVar("T", bound="PackDetail")



@_attrs_define
class PackDetail:
    """ 
        Attributes:
            id (None | str): Null for a pack without a header.
            name (None | PackDetailNameType1 | str): A string, or texts by language: {"en": …, "ro": …}.
            yaml (str):
            counts (PackDetailCounts | Unset): Items per section.
            description (None | PackDetailDescriptionType1 | str | Unset):
            parameters (list[PackParameterOut] | Unset):
            tags (list[str] | Unset):
            version (None | str | Unset):
     """

    id: None | str
    name: None | PackDetailNameType1 | str
    yaml: str
    counts: PackDetailCounts | Unset = UNSET
    description: None | PackDetailDescriptionType1 | str | Unset = UNSET
    parameters: list[PackParameterOut] | Unset = UNSET
    tags: list[str] | Unset = UNSET
    version: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pack_detail_counts import PackDetailCounts # noqa: PLC0415
        from ..models.pack_detail_description_type_1 import PackDetailDescriptionType1 # noqa: PLC0415
        from ..models.pack_detail_name_type_1 import PackDetailNameType1 # noqa: PLC0415
        from ..models.pack_parameter_out import PackParameterOut # noqa: PLC0415
        id: None | str
        id = self.id

        name: dict[str, Any] | None | str
        if isinstance(self.name, PackDetailNameType1):
            name = self.name.to_dict()
        else:
            name = self.name

        yaml = self.yaml

        counts: dict[str, Any] | Unset = UNSET
        if not isinstance(self.counts, Unset):
            counts = self.counts.to_dict()

        description: dict[str, Any] | None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        elif isinstance(self.description, PackDetailDescriptionType1):
            description = self.description.to_dict()
        else:
            description = self.description

        parameters: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.parameters, Unset):
            parameters = []
            for parameters_item_data in self.parameters:
                parameters_item = parameters_item_data.to_dict()
                parameters.append(parameters_item)



        tags: list[str] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags



        version: None | str | Unset
        if isinstance(self.version, Unset):
            version = UNSET
        else:
            version = self.version


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "name": name,
            "yaml": yaml,
        })
        if counts is not UNSET:
            field_dict["counts"] = counts
        if description is not UNSET:
            field_dict["description"] = description
        if parameters is not UNSET:
            field_dict["parameters"] = parameters
        if tags is not UNSET:
            field_dict["tags"] = tags
        if version is not UNSET:
            field_dict["version"] = version

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pack_detail_counts import PackDetailCounts # noqa: PLC0415
        from ..models.pack_detail_description_type_1 import PackDetailDescriptionType1 # noqa: PLC0415
        from ..models.pack_detail_name_type_1 import PackDetailNameType1 # noqa: PLC0415
        from ..models.pack_parameter_out import PackParameterOut # noqa: PLC0415
        d = dict(src_dict)
        def _parse_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        id = _parse_id(d.pop("id"))


        def _parse_name(data: object) -> None | PackDetailNameType1 | str:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                name_type_1 = PackDetailNameType1.from_dict(data)



                return name_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PackDetailNameType1 | str, data)

        name = _parse_name(d.pop("name"))


        yaml = d.pop("yaml")

        _counts = d.pop("counts", UNSET)
        counts: PackDetailCounts | Unset
        if isinstance(_counts,  Unset):
            counts = UNSET
        else:
            counts = PackDetailCounts.from_dict(_counts)




        def _parse_description(data: object) -> None | PackDetailDescriptionType1 | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                description_type_1 = PackDetailDescriptionType1.from_dict(data)



                return description_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PackDetailDescriptionType1 | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        _parameters = d.pop("parameters", UNSET)
        parameters: list[PackParameterOut] | Unset = UNSET
        if _parameters is not UNSET:
            parameters = []
            for parameters_item_data in _parameters:
                parameters_item = PackParameterOut.from_dict(parameters_item_data)



                parameters.append(parameters_item)


        tags = cast(list[str], d.pop("tags", UNSET))


        def _parse_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        version = _parse_version(d.pop("version", UNSET))


        pack_detail = cls(
            id=id,
            name=name,
            yaml=yaml,
            counts=counts,
            description=description,
            parameters=parameters,
            tags=tags,
            version=version,
        )


        pack_detail.additional_properties = d
        return pack_detail

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
