from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.rule_update_for_each_type_0 import RuleUpdateForEachType0





T = TypeVar("T", bound="RuleUpdate")



@_attrs_define
class RuleUpdate:
    """ 
        Attributes:
            condition_expr (None | str | Unset):
            enabled (bool | None | Unset):
            eval_interval_sec (int | None | Unset):
            for_each (None | RuleUpdateForEachType0 | Unset):
            incident_enabled (bool | None | Unset):
            inhibited_by (list[str] | None | Unset):
            persist_n (int | None | Unset):
            recovery_expr (None | str | Unset):
            recovery_persist_n (int | None | Unset):
            resolved_template_type (None | str | Unset):
            sort_order (int | None | Unset):
            template_type (None | str | Unset):
            trigger_logic_md (None | str | Unset):
            trigger_summary (None | str | Unset):
            vars_extract (list[str] | None | Unset):
     """

    condition_expr: None | str | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    eval_interval_sec: int | None | Unset = UNSET
    for_each: None | RuleUpdateForEachType0 | Unset = UNSET
    incident_enabled: bool | None | Unset = UNSET
    inhibited_by: list[str] | None | Unset = UNSET
    persist_n: int | None | Unset = UNSET
    recovery_expr: None | str | Unset = UNSET
    recovery_persist_n: int | None | Unset = UNSET
    resolved_template_type: None | str | Unset = UNSET
    sort_order: int | None | Unset = UNSET
    template_type: None | str | Unset = UNSET
    trigger_logic_md: None | str | Unset = UNSET
    trigger_summary: None | str | Unset = UNSET
    vars_extract: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.rule_update_for_each_type_0 import RuleUpdateForEachType0 # noqa: PLC0415
        condition_expr: None | str | Unset
        if isinstance(self.condition_expr, Unset):
            condition_expr = UNSET
        else:
            condition_expr = self.condition_expr

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        eval_interval_sec: int | None | Unset
        if isinstance(self.eval_interval_sec, Unset):
            eval_interval_sec = UNSET
        else:
            eval_interval_sec = self.eval_interval_sec

        for_each: dict[str, Any] | None | Unset
        if isinstance(self.for_each, Unset):
            for_each = UNSET
        elif isinstance(self.for_each, RuleUpdateForEachType0):
            for_each = self.for_each.to_dict()
        else:
            for_each = self.for_each

        incident_enabled: bool | None | Unset
        if isinstance(self.incident_enabled, Unset):
            incident_enabled = UNSET
        else:
            incident_enabled = self.incident_enabled

        inhibited_by: list[str] | None | Unset
        if isinstance(self.inhibited_by, Unset):
            inhibited_by = UNSET
        elif isinstance(self.inhibited_by, list):
            inhibited_by = self.inhibited_by


        else:
            inhibited_by = self.inhibited_by

        persist_n: int | None | Unset
        if isinstance(self.persist_n, Unset):
            persist_n = UNSET
        else:
            persist_n = self.persist_n

        recovery_expr: None | str | Unset
        if isinstance(self.recovery_expr, Unset):
            recovery_expr = UNSET
        else:
            recovery_expr = self.recovery_expr

        recovery_persist_n: int | None | Unset
        if isinstance(self.recovery_persist_n, Unset):
            recovery_persist_n = UNSET
        else:
            recovery_persist_n = self.recovery_persist_n

        resolved_template_type: None | str | Unset
        if isinstance(self.resolved_template_type, Unset):
            resolved_template_type = UNSET
        else:
            resolved_template_type = self.resolved_template_type

        sort_order: int | None | Unset
        if isinstance(self.sort_order, Unset):
            sort_order = UNSET
        else:
            sort_order = self.sort_order

        template_type: None | str | Unset
        if isinstance(self.template_type, Unset):
            template_type = UNSET
        else:
            template_type = self.template_type

        trigger_logic_md: None | str | Unset
        if isinstance(self.trigger_logic_md, Unset):
            trigger_logic_md = UNSET
        else:
            trigger_logic_md = self.trigger_logic_md

        trigger_summary: None | str | Unset
        if isinstance(self.trigger_summary, Unset):
            trigger_summary = UNSET
        else:
            trigger_summary = self.trigger_summary

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
        })
        if condition_expr is not UNSET:
            field_dict["condition_expr"] = condition_expr
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if eval_interval_sec is not UNSET:
            field_dict["eval_interval_sec"] = eval_interval_sec
        if for_each is not UNSET:
            field_dict["for_each"] = for_each
        if incident_enabled is not UNSET:
            field_dict["incident_enabled"] = incident_enabled
        if inhibited_by is not UNSET:
            field_dict["inhibited_by"] = inhibited_by
        if persist_n is not UNSET:
            field_dict["persist_n"] = persist_n
        if recovery_expr is not UNSET:
            field_dict["recovery_expr"] = recovery_expr
        if recovery_persist_n is not UNSET:
            field_dict["recovery_persist_n"] = recovery_persist_n
        if resolved_template_type is not UNSET:
            field_dict["resolved_template_type"] = resolved_template_type
        if sort_order is not UNSET:
            field_dict["sort_order"] = sort_order
        if template_type is not UNSET:
            field_dict["template_type"] = template_type
        if trigger_logic_md is not UNSET:
            field_dict["trigger_logic_md"] = trigger_logic_md
        if trigger_summary is not UNSET:
            field_dict["trigger_summary"] = trigger_summary
        if vars_extract is not UNSET:
            field_dict["vars_extract"] = vars_extract

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rule_update_for_each_type_0 import RuleUpdateForEachType0 # noqa: PLC0415
        d = dict(src_dict)
        def _parse_condition_expr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        condition_expr = _parse_condition_expr(d.pop("condition_expr", UNSET))


        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))


        def _parse_eval_interval_sec(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        eval_interval_sec = _parse_eval_interval_sec(d.pop("eval_interval_sec", UNSET))


        def _parse_for_each(data: object) -> None | RuleUpdateForEachType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                for_each_type_0 = RuleUpdateForEachType0.from_dict(data)



                return for_each_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RuleUpdateForEachType0 | Unset, data)

        for_each = _parse_for_each(d.pop("for_each", UNSET))


        def _parse_incident_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        incident_enabled = _parse_incident_enabled(d.pop("incident_enabled", UNSET))


        def _parse_inhibited_by(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                inhibited_by_type_0 = cast(list[str], data)

                return inhibited_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        inhibited_by = _parse_inhibited_by(d.pop("inhibited_by", UNSET))


        def _parse_persist_n(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        persist_n = _parse_persist_n(d.pop("persist_n", UNSET))


        def _parse_recovery_expr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        recovery_expr = _parse_recovery_expr(d.pop("recovery_expr", UNSET))


        def _parse_recovery_persist_n(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        recovery_persist_n = _parse_recovery_persist_n(d.pop("recovery_persist_n", UNSET))


        def _parse_resolved_template_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resolved_template_type = _parse_resolved_template_type(d.pop("resolved_template_type", UNSET))


        def _parse_sort_order(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        sort_order = _parse_sort_order(d.pop("sort_order", UNSET))


        def _parse_template_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        template_type = _parse_template_type(d.pop("template_type", UNSET))


        def _parse_trigger_logic_md(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trigger_logic_md = _parse_trigger_logic_md(d.pop("trigger_logic_md", UNSET))


        def _parse_trigger_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trigger_summary = _parse_trigger_summary(d.pop("trigger_summary", UNSET))


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


        rule_update = cls(
            condition_expr=condition_expr,
            enabled=enabled,
            eval_interval_sec=eval_interval_sec,
            for_each=for_each,
            incident_enabled=incident_enabled,
            inhibited_by=inhibited_by,
            persist_n=persist_n,
            recovery_expr=recovery_expr,
            recovery_persist_n=recovery_persist_n,
            resolved_template_type=resolved_template_type,
            sort_order=sort_order,
            template_type=template_type,
            trigger_logic_md=trigger_logic_md,
            trigger_summary=trigger_summary,
            vars_extract=vars_extract,
        )


        rule_update.additional_properties = d
        return rule_update

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
