from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.snooze_create_scope import SnoozeCreateScope
from ..types import UNSET, Unset
from typing import cast
import datetime






T = TypeVar("T", bound="SnoozeCreate")



@_attrs_define
class SnoozeCreate:
    """ Caller-supplied fields. ``created_by`` is filled server-side
    from the resolved Actor; ``id`` / ``created_at`` are DB-generated.

        Attributes:
            scope (SnoozeCreateScope):
            target (str):
            until (datetime.datetime):
            reason (None | str | Unset):
     """

    scope: SnoozeCreateScope
    target: str
    until: datetime.datetime
    reason: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        scope = self.scope.value

        target = self.target

        until = self.until.isoformat()

        reason: None | str | Unset
        if isinstance(self.reason, Unset):
            reason = UNSET
        else:
            reason = self.reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "scope": scope,
            "target": target,
            "until": until,
        })
        if reason is not UNSET:
            field_dict["reason"] = reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        scope = SnoozeCreateScope(d.pop("scope"))




        target = d.pop("target")

        until = datetime.datetime.fromisoformat(d.pop("until"))




        def _parse_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reason = _parse_reason(d.pop("reason", UNSET))


        snooze_create = cls(
            scope=scope,
            target=target,
            until=until,
            reason=reason,
        )


        snooze_create.additional_properties = d
        return snooze_create

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
