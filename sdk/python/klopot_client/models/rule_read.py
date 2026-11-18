from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.rule_read_eval_status import RuleReadEvalStatus
from ..models.rule_run_state import RuleRunState
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.rule_read_for_each_type_0 import RuleReadForEachType0





T = TypeVar("T", bound="RuleRead")



@_attrs_define
class RuleRead:
    """ 
        Attributes:
            condition_expr (str):
            created_at (None | str):
            eval_status (RuleReadEvalStatus): ``error``: the expression fails (counted towards auto-disable);
                ``no_data``: it is waiting for an input that has no value; ``ok``.
            id (int):
            name (str):
            template_type (str):
            updated_at (None | str):
            consecutive_eval_errors (int | Unset):  Default: 0.
            enabled (bool | Unset):  Default: True.
            eval_interval_sec (int | Unset):  Default: 10.
            fire_count_lifetime (int | Unset):  Default: 0.
            for_each (None | RuleReadForEachType0 | Unset): Parametric rule (ADR-0005): one parameter and its values, {"n":
                ["f1", "f2"]}. The rule runs once per value, {n} replaced in condition_expr, recovery_expr, vars_extract,
                template_type and resolved_template_type; the template sees n. null = an ordinary rule.
            incident_enabled (bool | Unset):  Default: False.
            inhibited_by (list[str] | Unset):
            last_eval_error (None | str | Unset):
            last_evaluated_at (None | str | Unset):
            last_fired_at (None | str | Unset):
            last_true_at (None | str | Unset): When the condition last became true.
            persist_n (int | Unset):  Default: 1.
            recovery_expr (None | str | Unset):
            recovery_persist_n (int | Unset):  Default: 1.
            resolved_template_type (None | str | Unset):
            run_state (None | RuleRunState | Unset): Where the rule is in its cycle at its last evaluation: inactive
                (condition false), pending (true, persist_n not reached), firing (fired and still true; an incident rule: its
                incident is open), no_data, error. null until its first evaluation, and after an edit of the condition until the
                new one is evaluated.
            run_state_since (None | str | Unset):
            sort_order (int | Unset):  Default: 100.
            trigger_logic_md (None | str | Unset):
            trigger_summary (None | str | Unset):
            vars_extract (list[str] | Unset):
     """

    condition_expr: str
    created_at: None | str
    eval_status: RuleReadEvalStatus
    id: int
    name: str
    template_type: str
    updated_at: None | str
    consecutive_eval_errors: int | Unset = 0
    enabled: bool | Unset = True
    eval_interval_sec: int | Unset = 10
    fire_count_lifetime: int | Unset = 0
    for_each: None | RuleReadForEachType0 | Unset = UNSET
    incident_enabled: bool | Unset = False
    inhibited_by: list[str] | Unset = UNSET
    last_eval_error: None | str | Unset = UNSET
    last_evaluated_at: None | str | Unset = UNSET
    last_fired_at: None | str | Unset = UNSET
    last_true_at: None | str | Unset = UNSET
    persist_n: int | Unset = 1
    recovery_expr: None | str | Unset = UNSET
    recovery_persist_n: int | Unset = 1
    resolved_template_type: None | str | Unset = UNSET
    run_state: None | RuleRunState | Unset = UNSET
    run_state_since: None | str | Unset = UNSET
    sort_order: int | Unset = 100
    trigger_logic_md: None | str | Unset = UNSET
    trigger_summary: None | str | Unset = UNSET
    vars_extract: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.rule_read_for_each_type_0 import RuleReadForEachType0 # noqa: PLC0415
        condition_expr = self.condition_expr

        created_at: None | str
        created_at = self.created_at

        eval_status = self.eval_status.value

        id = self.id

        name = self.name

        template_type = self.template_type

        updated_at: None | str
        updated_at = self.updated_at

        consecutive_eval_errors = self.consecutive_eval_errors

        enabled = self.enabled

        eval_interval_sec = self.eval_interval_sec

        fire_count_lifetime = self.fire_count_lifetime

        for_each: dict[str, Any] | None | Unset
        if isinstance(self.for_each, Unset):
            for_each = UNSET
        elif isinstance(self.for_each, RuleReadForEachType0):
            for_each = self.for_each.to_dict()
        else:
            for_each = self.for_each

        incident_enabled = self.incident_enabled

        inhibited_by: list[str] | Unset = UNSET
        if not isinstance(self.inhibited_by, Unset):
            inhibited_by = self.inhibited_by



        last_eval_error: None | str | Unset
        if isinstance(self.last_eval_error, Unset):
            last_eval_error = UNSET
        else:
            last_eval_error = self.last_eval_error

        last_evaluated_at: None | str | Unset
        if isinstance(self.last_evaluated_at, Unset):
            last_evaluated_at = UNSET
        else:
            last_evaluated_at = self.last_evaluated_at

        last_fired_at: None | str | Unset
        if isinstance(self.last_fired_at, Unset):
            last_fired_at = UNSET
        else:
            last_fired_at = self.last_fired_at

        last_true_at: None | str | Unset
        if isinstance(self.last_true_at, Unset):
            last_true_at = UNSET
        else:
            last_true_at = self.last_true_at

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

        run_state: None | str | Unset
        if isinstance(self.run_state, Unset):
            run_state = UNSET
        elif isinstance(self.run_state, RuleRunState):
            run_state = self.run_state.value
        else:
            run_state = self.run_state

        run_state_since: None | str | Unset
        if isinstance(self.run_state_since, Unset):
            run_state_since = UNSET
        else:
            run_state_since = self.run_state_since

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
            "created_at": created_at,
            "eval_status": eval_status,
            "id": id,
            "name": name,
            "template_type": template_type,
            "updated_at": updated_at,
        })
        if consecutive_eval_errors is not UNSET:
            field_dict["consecutive_eval_errors"] = consecutive_eval_errors
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if eval_interval_sec is not UNSET:
            field_dict["eval_interval_sec"] = eval_interval_sec
        if fire_count_lifetime is not UNSET:
            field_dict["fire_count_lifetime"] = fire_count_lifetime
        if for_each is not UNSET:
            field_dict["for_each"] = for_each
        if incident_enabled is not UNSET:
            field_dict["incident_enabled"] = incident_enabled
        if inhibited_by is not UNSET:
            field_dict["inhibited_by"] = inhibited_by
        if last_eval_error is not UNSET:
            field_dict["last_eval_error"] = last_eval_error
        if last_evaluated_at is not UNSET:
            field_dict["last_evaluated_at"] = last_evaluated_at
        if last_fired_at is not UNSET:
            field_dict["last_fired_at"] = last_fired_at
        if last_true_at is not UNSET:
            field_dict["last_true_at"] = last_true_at
        if persist_n is not UNSET:
            field_dict["persist_n"] = persist_n
        if recovery_expr is not UNSET:
            field_dict["recovery_expr"] = recovery_expr
        if recovery_persist_n is not UNSET:
            field_dict["recovery_persist_n"] = recovery_persist_n
        if resolved_template_type is not UNSET:
            field_dict["resolved_template_type"] = resolved_template_type
        if run_state is not UNSET:
            field_dict["run_state"] = run_state
        if run_state_since is not UNSET:
            field_dict["run_state_since"] = run_state_since
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
        from ..models.rule_read_for_each_type_0 import RuleReadForEachType0 # noqa: PLC0415
        d = dict(src_dict)
        condition_expr = d.pop("condition_expr")

        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        eval_status = RuleReadEvalStatus(d.pop("eval_status"))




        id = d.pop("id")

        name = d.pop("name")

        template_type = d.pop("template_type")

        def _parse_updated_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))


        consecutive_eval_errors = d.pop("consecutive_eval_errors", UNSET)

        enabled = d.pop("enabled", UNSET)

        eval_interval_sec = d.pop("eval_interval_sec", UNSET)

        fire_count_lifetime = d.pop("fire_count_lifetime", UNSET)

        def _parse_for_each(data: object) -> None | RuleReadForEachType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                for_each_type_0 = RuleReadForEachType0.from_dict(data)



                return for_each_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RuleReadForEachType0 | Unset, data)

        for_each = _parse_for_each(d.pop("for_each", UNSET))


        incident_enabled = d.pop("incident_enabled", UNSET)

        inhibited_by = cast(list[str], d.pop("inhibited_by", UNSET))


        def _parse_last_eval_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_eval_error = _parse_last_eval_error(d.pop("last_eval_error", UNSET))


        def _parse_last_evaluated_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_evaluated_at = _parse_last_evaluated_at(d.pop("last_evaluated_at", UNSET))


        def _parse_last_fired_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_fired_at = _parse_last_fired_at(d.pop("last_fired_at", UNSET))


        def _parse_last_true_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_true_at = _parse_last_true_at(d.pop("last_true_at", UNSET))


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


        def _parse_run_state(data: object) -> None | RuleRunState | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                run_state_type_0 = RuleRunState(data)



                return run_state_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RuleRunState | Unset, data)

        run_state = _parse_run_state(d.pop("run_state", UNSET))


        def _parse_run_state_since(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        run_state_since = _parse_run_state_since(d.pop("run_state_since", UNSET))


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


        rule_read = cls(
            condition_expr=condition_expr,
            created_at=created_at,
            eval_status=eval_status,
            id=id,
            name=name,
            template_type=template_type,
            updated_at=updated_at,
            consecutive_eval_errors=consecutive_eval_errors,
            enabled=enabled,
            eval_interval_sec=eval_interval_sec,
            fire_count_lifetime=fire_count_lifetime,
            for_each=for_each,
            incident_enabled=incident_enabled,
            inhibited_by=inhibited_by,
            last_eval_error=last_eval_error,
            last_evaluated_at=last_evaluated_at,
            last_fired_at=last_fired_at,
            last_true_at=last_true_at,
            persist_n=persist_n,
            recovery_expr=recovery_expr,
            recovery_persist_n=recovery_persist_n,
            resolved_template_type=resolved_template_type,
            run_state=run_state,
            run_state_since=run_state_since,
            sort_order=sort_order,
            trigger_logic_md=trigger_logic_md,
            trigger_summary=trigger_summary,
            vars_extract=vars_extract,
        )


        rule_read.additional_properties = d
        return rule_read

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
