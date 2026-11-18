from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.rule_run_state import RuleRunState
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RuleInstanceRead")



@_attrs_define
class RuleInstanceRead:
    """ One instance of a rule (``GET /v1/rules/{id}/instances``).

        Attributes:
            instance (str):
            consecutive_match_count (int | Unset):  Default: 0.
            last_eval_error (None | str | Unset):
            last_true_at (None | str | Unset):
            run_state (None | RuleRunState | Unset):
            run_state_since (None | str | Unset):
     """

    instance: str
    consecutive_match_count: int | Unset = 0
    last_eval_error: None | str | Unset = UNSET
    last_true_at: None | str | Unset = UNSET
    run_state: None | RuleRunState | Unset = UNSET
    run_state_since: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        instance = self.instance

        consecutive_match_count = self.consecutive_match_count

        last_eval_error: None | str | Unset
        if isinstance(self.last_eval_error, Unset):
            last_eval_error = UNSET
        else:
            last_eval_error = self.last_eval_error

        last_true_at: None | str | Unset
        if isinstance(self.last_true_at, Unset):
            last_true_at = UNSET
        else:
            last_true_at = self.last_true_at

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


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "instance": instance,
        })
        if consecutive_match_count is not UNSET:
            field_dict["consecutive_match_count"] = consecutive_match_count
        if last_eval_error is not UNSET:
            field_dict["last_eval_error"] = last_eval_error
        if last_true_at is not UNSET:
            field_dict["last_true_at"] = last_true_at
        if run_state is not UNSET:
            field_dict["run_state"] = run_state
        if run_state_since is not UNSET:
            field_dict["run_state_since"] = run_state_since

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        instance = d.pop("instance")

        consecutive_match_count = d.pop("consecutive_match_count", UNSET)

        def _parse_last_eval_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_eval_error = _parse_last_eval_error(d.pop("last_eval_error", UNSET))


        def _parse_last_true_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_true_at = _parse_last_true_at(d.pop("last_true_at", UNSET))


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


        rule_instance_read = cls(
            instance=instance,
            consecutive_match_count=consecutive_match_count,
            last_eval_error=last_eval_error,
            last_true_at=last_true_at,
            run_state=run_state,
            run_state_since=run_state_since,
        )


        rule_instance_read.additional_properties = d
        return rule_instance_read

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
