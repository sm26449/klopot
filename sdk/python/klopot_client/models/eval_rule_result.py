from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.eval_rule_result_context import EvalRuleResultContext





T = TypeVar("T", bound="EvalRuleResult")



@_attrs_define
class EvalRuleResult:
    """ ``POST /v1/rules/{id}/eval-now`` response.

        Attributes:
            consecutive_match_count (int):
            context (EvalRuleResultContext):
            matched (bool):
            error (None | str | Unset):
            instance (str | Unset):  Default: ''.
            missing_vars (list[str] | None | Unset):
     """

    consecutive_match_count: int
    context: EvalRuleResultContext
    matched: bool
    error: None | str | Unset = UNSET
    instance: str | Unset = ''
    missing_vars: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.eval_rule_result_context import EvalRuleResultContext # noqa: PLC0415
        consecutive_match_count = self.consecutive_match_count

        context = self.context.to_dict()

        matched = self.matched

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        instance = self.instance

        missing_vars: list[str] | None | Unset
        if isinstance(self.missing_vars, Unset):
            missing_vars = UNSET
        elif isinstance(self.missing_vars, list):
            missing_vars = self.missing_vars


        else:
            missing_vars = self.missing_vars


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "consecutive_match_count": consecutive_match_count,
            "context": context,
            "matched": matched,
        })
        if error is not UNSET:
            field_dict["error"] = error
        if instance is not UNSET:
            field_dict["instance"] = instance
        if missing_vars is not UNSET:
            field_dict["missing_vars"] = missing_vars

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.eval_rule_result_context import EvalRuleResultContext # noqa: PLC0415
        d = dict(src_dict)
        consecutive_match_count = d.pop("consecutive_match_count")

        context = EvalRuleResultContext.from_dict(d.pop("context"))




        matched = d.pop("matched")

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))


        instance = d.pop("instance", UNSET)

        def _parse_missing_vars(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                missing_vars_type_0 = cast(list[str], data)

                return missing_vars_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        missing_vars = _parse_missing_vars(d.pop("missing_vars", UNSET))


        eval_rule_result = cls(
            consecutive_match_count=consecutive_match_count,
            context=context,
            matched=matched,
            error=error,
            instance=instance,
            missing_vars=missing_vars,
        )


        eval_rule_result.additional_properties = d
        return eval_rule_result

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
