from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RuleCreate")



@_attrs_define
class RuleCreate:
    """ 
        Attributes:
            condition_expr (str):
            name (str):
            template_type (str):
            enabled (bool | Unset):  Default: True.
            eval_interval_sec (int | Unset):  Default: 10.
            incident_enabled (bool | Unset):  Default: False.
            inhibited_by (list[str] | Unset):
            persist_n (int | Unset):  Default: 1.
            recovery_expr (None | str | Unset):
            recovery_persist_n (int | Unset):  Default: 1.
            resolved_template_type (None | str | Unset):
            sort_order (int | Unset):  Default: 100.
            trigger_logic_md (None | str | Unset):
            trigger_summary (None | str | Unset):
            vars_extract (list[str] | Unset):
     """

    condition_expr: str
    name: str
    template_type: str
    enabled: bool | Unset = True
    eval_interval_sec: int | Unset = 10
    incident_enabled: bool | Unset = False
    inhibited_by: list[str] | Unset = UNSET
    persist_n: int | Unset = 1
    recovery_expr: None | str | Unset = UNSET
    recovery_persist_n: int | Unset = 1
    resolved_template_type: None | str | Unset = UNSET
    sort_order: int | Unset = 100
    trigger_logic_md: None | str | Unset = UNSET
    trigger_summary: None | str | Unset = UNSET
    vars_extract: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        condition_expr = self.condition_expr

        name = self.name

        template_type = self.template_type

        enabled = self.enabled

        eval_interval_sec = self.eval_interval_sec

        incident_enabled = self.incident_enabled

        inhibited_by: list[str] | Unset = UNSET
        if not isinstance(self.inhibited_by, Unset):
            inhibited_by = self.inhibited_by



        persist_n = self.persist_n

        recovery_expr: None | str | Unset
        if isinstance(self.recovery_expr, Unset):
            recovery_expr = UNSET
        else:
            recovery_expr = self.recovery_expr

        recovery_persist_n = self.recovery_persist_n

        resolved_template_type: None | str | Unset
        if isinstance(self.resolved_template_type, Unset):
            resolved_template_type = UNSET
        else:
            resolved_template_type = self.resolved_template_type

        sort_order = self.sort_order

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

        vars_extract: list[str] | Unset = UNSET
        if not isinstance(self.vars_extract, Unset):
            vars_extract = self.vars_extract




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "condition_expr": condition_expr,
            "name": name,
            "template_type": template_type,
        })
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if eval_interval_sec is not UNSET:
            field_dict["eval_interval_sec"] = eval_interval_sec
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
        if trigger_logic_md is not UNSET:
            field_dict["trigger_logic_md"] = trigger_logic_md
        if trigger_summary is not UNSET:
            field_dict["trigger_summary"] = trigger_summary
        if vars_extract is not UNSET:
            field_dict["vars_extract"] = vars_extract

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        condition_expr = d.pop("condition_expr")

        name = d.pop("name")

        template_type = d.pop("template_type")

        enabled = d.pop("enabled", UNSET)

        eval_interval_sec = d.pop("eval_interval_sec", UNSET)

        incident_enabled = d.pop("incident_enabled", UNSET)

        inhibited_by = cast(list[str], d.pop("inhibited_by", UNSET))


        persist_n = d.pop("persist_n", UNSET)

        def _parse_recovery_expr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        recovery_expr = _parse_recovery_expr(d.pop("recovery_expr", UNSET))


        recovery_persist_n = d.pop("recovery_persist_n", UNSET)

        def _parse_resolved_template_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resolved_template_type = _parse_resolved_template_type(d.pop("resolved_template_type", UNSET))


        sort_order = d.pop("sort_order", UNSET)

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


        vars_extract = cast(list[str], d.pop("vars_extract", UNSET))


        rule_create = cls(
            condition_expr=condition_expr,
            name=name,
            template_type=template_type,
            enabled=enabled,
            eval_interval_sec=eval_interval_sec,
            incident_enabled=incident_enabled,
            inhibited_by=inhibited_by,
            persist_n=persist_n,
            recovery_expr=recovery_expr,
            recovery_persist_n=recovery_persist_n,
            resolved_template_type=resolved_template_type,
            sort_order=sort_order,
            trigger_logic_md=trigger_logic_md,
            trigger_summary=trigger_summary,
            vars_extract=vars_extract,
        )


        rule_create.additional_properties = d
        return rule_create

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
