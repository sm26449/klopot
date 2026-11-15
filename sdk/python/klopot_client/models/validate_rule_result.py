from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.referenced_var import ReferencedVar





T = TypeVar("T", bound="ValidateRuleResult")



@_attrs_define
class ValidateRuleResult:
    """ 
        Attributes:
            ok (bool):
            error (None | str | Unset):
            referenced_vars (list[ReferencedVar] | Unset):
            result (Any | Unset):
            unknown_vars (list[str] | Unset):
     """

    ok: bool
    error: None | str | Unset = UNSET
    referenced_vars: list[ReferencedVar] | Unset = UNSET
    result: Any | Unset = UNSET
    unknown_vars: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.referenced_var import ReferencedVar # noqa: PLC0415
        ok = self.ok

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        referenced_vars: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.referenced_vars, Unset):
            referenced_vars = []
            for referenced_vars_item_data in self.referenced_vars:
                referenced_vars_item = referenced_vars_item_data.to_dict()
                referenced_vars.append(referenced_vars_item)



        result = self.result

        unknown_vars: list[str] | Unset = UNSET
        if not isinstance(self.unknown_vars, Unset):
            unknown_vars = self.unknown_vars




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "ok": ok,
        })
        if error is not UNSET:
            field_dict["error"] = error
        if referenced_vars is not UNSET:
            field_dict["referenced_vars"] = referenced_vars
        if result is not UNSET:
            field_dict["result"] = result
        if unknown_vars is not UNSET:
            field_dict["unknown_vars"] = unknown_vars

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.referenced_var import ReferencedVar # noqa: PLC0415
        d = dict(src_dict)
        ok = d.pop("ok")

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))


        _referenced_vars = d.pop("referenced_vars", UNSET)
        referenced_vars: list[ReferencedVar] | Unset = UNSET
        if _referenced_vars is not UNSET:
            referenced_vars = []
            for referenced_vars_item_data in _referenced_vars:
                referenced_vars_item = ReferencedVar.from_dict(referenced_vars_item_data)



                referenced_vars.append(referenced_vars_item)


        result = d.pop("result", UNSET)

        unknown_vars = cast(list[str], d.pop("unknown_vars", UNSET))


        validate_rule_result = cls(
            ok=ok,
            error=error,
            referenced_vars=referenced_vars,
            result=result,
            unknown_vars=unknown_vars,
        )


        validate_rule_result.additional_properties = d
        return validate_rule_result

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
