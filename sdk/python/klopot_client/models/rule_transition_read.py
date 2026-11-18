from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.rule_run_state import RuleRunState
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="RuleTransitionRead")



@_attrs_define
class RuleTransitionRead:
    """ One change of a rule's run state (``GET /v1/rules/{id}/transitions``).

        Attributes:
            at (None | str):
            to_state (RuleRunState): Where a rule is in its cycle (rules review RL-32), as the engine saw
                it at the last evaluation: ``pending`` = the condition holds but
                ``persist_n`` is not reached yet; ``firing`` = it fired (an incident rule:
                its incident is open) and still holds.
            detail (None | str | Unset):
            from_state (None | RuleRunState | Unset):
            instance (str | Unset): The instance of a parametric rule; "" otherwise. Default: ''.
     """

    at: None | str
    to_state: RuleRunState
    detail: None | str | Unset = UNSET
    from_state: None | RuleRunState | Unset = UNSET
    instance: str | Unset = ''
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        at: None | str
        at = self.at

        to_state = self.to_state.value

        detail: None | str | Unset
        if isinstance(self.detail, Unset):
            detail = UNSET
        else:
            detail = self.detail

        from_state: None | str | Unset
        if isinstance(self.from_state, Unset):
            from_state = UNSET
        elif isinstance(self.from_state, RuleRunState):
            from_state = self.from_state.value
        else:
            from_state = self.from_state

        instance = self.instance


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "at": at,
            "to_state": to_state,
        })
        if detail is not UNSET:
            field_dict["detail"] = detail
        if from_state is not UNSET:
            field_dict["from_state"] = from_state
        if instance is not UNSET:
            field_dict["instance"] = instance

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        at = _parse_at(d.pop("at"))


        to_state = RuleRunState(d.pop("to_state"))




        def _parse_detail(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        detail = _parse_detail(d.pop("detail", UNSET))


        def _parse_from_state(data: object) -> None | RuleRunState | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                from_state_type_0 = RuleRunState(data)



                return from_state_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RuleRunState | Unset, data)

        from_state = _parse_from_state(d.pop("from_state", UNSET))


        instance = d.pop("instance", UNSET)

        rule_transition_read = cls(
            at=at,
            to_state=to_state,
            detail=detail,
            from_state=from_state,
            instance=instance,
        )


        rule_transition_read.additional_properties = d
        return rule_transition_read

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
