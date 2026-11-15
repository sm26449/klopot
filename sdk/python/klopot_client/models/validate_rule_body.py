from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ValidateRuleBody")



@_attrs_define
class ValidateRuleBody:
    """ ``POST /v1/rules/validate`` body.

        Attributes:
            condition_expr (str):
            vars_extract (list[str] | None | Unset):
     """

    condition_expr: str
    vars_extract: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        condition_expr = self.condition_expr

        vars_extract: list[str] | None | Unset
        if isinstance(self.vars_extract, Unset):
            vars_extract = UNSET
        elif isinstance(self.vars_extract, list):
            vars_extract = self.vars_extract


        else:
            vars_extract = self.vars_extract


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "condition_expr": condition_expr,
        })
        if vars_extract is not UNSET:
            field_dict["vars_extract"] = vars_extract

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        condition_expr = d.pop("condition_expr")

        def _parse_vars_extract(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                vars_extract_type_0 = cast(list[str], data)

                return vars_extract_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        vars_extract = _parse_vars_extract(d.pop("vars_extract", UNSET))


        validate_rule_body = cls(
            condition_expr=condition_expr,
            vars_extract=vars_extract,
        )


        validate_rule_body.additional_properties = d
        return validate_rule_body

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
