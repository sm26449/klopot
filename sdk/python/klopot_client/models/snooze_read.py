from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.snooze_read_scope import SnoozeReadScope
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="SnoozeRead")



@_attrs_define
class SnoozeRead:
    """ 
        Attributes:
            created_at (None | str):
            id (int):
            scope (SnoozeReadScope):
            target (str):
            until (None | str):
            created_by (None | str | Unset):
            reason (None | str | Unset):
     """

    created_at: None | str
    id: int
    scope: SnoozeReadScope
    target: str
    until: None | str
    created_by: None | str | Unset = UNSET
    reason: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        created_at: None | str
        created_at = self.created_at

        id = self.id

        scope = self.scope.value

        target = self.target

        until: None | str
        until = self.until

        created_by: None | str | Unset
        if isinstance(self.created_by, Unset):
            created_by = UNSET
        else:
            created_by = self.created_by

        reason: None | str | Unset
        if isinstance(self.reason, Unset):
            reason = UNSET
        else:
            reason = self.reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "id": id,
            "scope": scope,
            "target": target,
            "until": until,
        })
        if created_by is not UNSET:
            field_dict["created_by"] = created_by
        if reason is not UNSET:
            field_dict["reason"] = reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        id = d.pop("id")

        scope = SnoozeReadScope(d.pop("scope"))




        target = d.pop("target")

        def _parse_until(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        until = _parse_until(d.pop("until"))


        def _parse_created_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        created_by = _parse_created_by(d.pop("created_by", UNSET))


        def _parse_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reason = _parse_reason(d.pop("reason", UNSET))


        snooze_read = cls(
            created_at=created_at,
            id=id,
            scope=scope,
            target=target,
            until=until,
            created_by=created_by,
            reason=reason,
        )


        snooze_read.additional_properties = d
        return snooze_read

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
