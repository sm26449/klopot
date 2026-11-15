from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.pack_parameter_out_description_type_1 import PackParameterOutDescriptionType1
  from ..models.pack_parameter_out_label_type_1 import PackParameterOutLabelType1





T = TypeVar("T", bound="PackParameterOut")



@_attrs_define
class PackParameterOut:
    """ 
        Attributes:
            name (str):
            required (bool):
            type_ (str):
            default (Any | Unset):
            description (None | PackParameterOutDescriptionType1 | str | Unset):
            example (Any | Unset):
            label (None | PackParameterOutLabelType1 | str | Unset):
     """

    name: str
    required: bool
    type_: str
    default: Any | Unset = UNSET
    description: None | PackParameterOutDescriptionType1 | str | Unset = UNSET
    example: Any | Unset = UNSET
    label: None | PackParameterOutLabelType1 | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pack_parameter_out_description_type_1 import PackParameterOutDescriptionType1 # noqa: PLC0415
        from ..models.pack_parameter_out_label_type_1 import PackParameterOutLabelType1 # noqa: PLC0415
        name = self.name

        required = self.required

        type_ = self.type_

        default = self.default

        description: dict[str, Any] | None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        elif isinstance(self.description, PackParameterOutDescriptionType1):
            description = self.description.to_dict()
        else:
            description = self.description

        example = self.example

        label: dict[str, Any] | None | str | Unset
        if isinstance(self.label, Unset):
            label = UNSET
        elif isinstance(self.label, PackParameterOutLabelType1):
            label = self.label.to_dict()
        else:
            label = self.label


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
            "required": required,
            "type": type_,
        })
        if default is not UNSET:
            field_dict["default"] = default
        if description is not UNSET:
            field_dict["description"] = description
        if example is not UNSET:
            field_dict["example"] = example
        if label is not UNSET:
            field_dict["label"] = label

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pack_parameter_out_description_type_1 import PackParameterOutDescriptionType1 # noqa: PLC0415
        from ..models.pack_parameter_out_label_type_1 import PackParameterOutLabelType1 # noqa: PLC0415
        d = dict(src_dict)
        name = d.pop("name")

        required = d.pop("required")

        type_ = d.pop("type")

        default = d.pop("default", UNSET)

        def _parse_description(data: object) -> None | PackParameterOutDescriptionType1 | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                description_type_1 = PackParameterOutDescriptionType1.from_dict(data)



                return description_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PackParameterOutDescriptionType1 | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        example = d.pop("example", UNSET)

        def _parse_label(data: object) -> None | PackParameterOutLabelType1 | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                label_type_1 = PackParameterOutLabelType1.from_dict(data)



                return label_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PackParameterOutLabelType1 | str | Unset, data)

        label = _parse_label(d.pop("label", UNSET))


        pack_parameter_out = cls(
            name=name,
            required=required,
            type_=type_,
            default=default,
            description=description,
            example=example,
            label=label,
        )


        pack_parameter_out.additional_properties = d
        return pack_parameter_out

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
