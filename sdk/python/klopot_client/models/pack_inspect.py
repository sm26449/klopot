from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.pack_inspect_counts import PackInspectCounts
  from ..models.pack_inspect_description_type_1 import PackInspectDescriptionType1
  from ..models.pack_inspect_name_type_1 import PackInspectNameType1
  from ..models.pack_parameter_out import PackParameterOut





T = TypeVar("T", bound="PackInspect")



@_attrs_define
class PackInspect:
    """ 
        Attributes:
            id (None | str): Null for a pack without a header.
            name (None | PackInspectNameType1 | str): A string, or texts by language: {"en": …, "ro": …}.
            ok (bool):
            counts (PackInspectCounts | Unset): Items per section.
            description (None | PackInspectDescriptionType1 | str | Unset):
            errors (list[str] | Unset):
            parameters (list[PackParameterOut] | Unset):
            tags (list[str] | Unset):
            version (None | str | Unset):
     """

    id: None | str
    name: None | PackInspectNameType1 | str
    ok: bool
    counts: PackInspectCounts | Unset = UNSET
    description: None | PackInspectDescriptionType1 | str | Unset = UNSET
    errors: list[str] | Unset = UNSET
    parameters: list[PackParameterOut] | Unset = UNSET
    tags: list[str] | Unset = UNSET
    version: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pack_inspect_counts import PackInspectCounts # noqa: PLC0415
        from ..models.pack_inspect_description_type_1 import PackInspectDescriptionType1 # noqa: PLC0415
        from ..models.pack_inspect_name_type_1 import PackInspectNameType1 # noqa: PLC0415
        from ..models.pack_parameter_out import PackParameterOut # noqa: PLC0415
        id: None | str
        id = self.id

        name: dict[str, Any] | None | str
        if isinstance(self.name, PackInspectNameType1):
            name = self.name.to_dict()
        else:
            name = self.name

        ok = self.ok

        counts: dict[str, Any] | Unset = UNSET
        if not isinstance(self.counts, Unset):
            counts = self.counts.to_dict()

        description: dict[str, Any] | None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        elif isinstance(self.description, PackInspectDescriptionType1):
            description = self.description.to_dict()
        else:
            description = self.description

        errors: list[str] | Unset = UNSET
        if not isinstance(self.errors, Unset):
            errors = self.errors



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
            "ok": ok,
        })
        if counts is not UNSET:
            field_dict["counts"] = counts
        if description is not UNSET:
            field_dict["description"] = description
        if errors is not UNSET:
            field_dict["errors"] = errors
        if parameters is not UNSET:
            field_dict["parameters"] = parameters
        if tags is not UNSET:
            field_dict["tags"] = tags
        if version is not UNSET:
            field_dict["version"] = version

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pack_inspect_counts import PackInspectCounts # noqa: PLC0415
        from ..models.pack_inspect_description_type_1 import PackInspectDescriptionType1 # noqa: PLC0415
        from ..models.pack_inspect_name_type_1 import PackInspectNameType1 # noqa: PLC0415
        from ..models.pack_parameter_out import PackParameterOut # noqa: PLC0415
        d = dict(src_dict)
        def _parse_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        id = _parse_id(d.pop("id"))


        def _parse_name(data: object) -> None | PackInspectNameType1 | str:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                name_type_1 = PackInspectNameType1.from_dict(data)



                return name_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PackInspectNameType1 | str, data)

        name = _parse_name(d.pop("name"))


        ok = d.pop("ok")

        _counts = d.pop("counts", UNSET)
        counts: PackInspectCounts | Unset
        if isinstance(_counts,  Unset):
            counts = UNSET
        else:
            counts = PackInspectCounts.from_dict(_counts)




        def _parse_description(data: object) -> None | PackInspectDescriptionType1 | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                description_type_1 = PackInspectDescriptionType1.from_dict(data)



                return description_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PackInspectDescriptionType1 | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        errors = cast(list[str], d.pop("errors", UNSET))


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


        pack_inspect = cls(
            id=id,
            name=name,
            ok=ok,
            counts=counts,
            description=description,
            errors=errors,
            parameters=parameters,
            tags=tags,
            version=version,
        )


        pack_inspect.additional_properties = d
        return pack_inspect

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
