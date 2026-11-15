from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.schedule_read_context import ScheduleReadContext





T = TypeVar("T", bound="ScheduleRead")



@_attrs_define
class ScheduleRead:
    """ 
        Attributes:
            created_at (None | str):
            cron_expr (str):
            id (int):
            name (str):
            template_type (str):
            updated_at (None | str):
            context (ScheduleReadContext | Unset):
            enabled (bool | Unset):  Default: True.
            last_fired_at (None | str | Unset):
            next_fire_at (None | str | Unset):
     """

    created_at: None | str
    cron_expr: str
    id: int
    name: str
    template_type: str
    updated_at: None | str
    context: ScheduleReadContext | Unset = UNSET
    enabled: bool | Unset = True
    last_fired_at: None | str | Unset = UNSET
    next_fire_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.schedule_read_context import ScheduleReadContext # noqa: PLC0415
        created_at: None | str
        created_at = self.created_at

        cron_expr = self.cron_expr

        id = self.id

        name = self.name

        template_type = self.template_type

        updated_at: None | str
        updated_at = self.updated_at

        context: dict[str, Any] | Unset = UNSET
        if not isinstance(self.context, Unset):
            context = self.context.to_dict()

        enabled = self.enabled

        last_fired_at: None | str | Unset
        if isinstance(self.last_fired_at, Unset):
            last_fired_at = UNSET
        else:
            last_fired_at = self.last_fired_at

        next_fire_at: None | str | Unset
        if isinstance(self.next_fire_at, Unset):
            next_fire_at = UNSET
        else:
            next_fire_at = self.next_fire_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "cron_expr": cron_expr,
            "id": id,
            "name": name,
            "template_type": template_type,
            "updated_at": updated_at,
        })
        if context is not UNSET:
            field_dict["context"] = context
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if last_fired_at is not UNSET:
            field_dict["last_fired_at"] = last_fired_at
        if next_fire_at is not UNSET:
            field_dict["next_fire_at"] = next_fire_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.schedule_read_context import ScheduleReadContext # noqa: PLC0415
        d = dict(src_dict)
        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        cron_expr = d.pop("cron_expr")

        id = d.pop("id")

        name = d.pop("name")

        template_type = d.pop("template_type")

        def _parse_updated_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))


        _context = d.pop("context", UNSET)
        context: ScheduleReadContext | Unset
        if isinstance(_context,  Unset):
            context = UNSET
        else:
            context = ScheduleReadContext.from_dict(_context)




        enabled = d.pop("enabled", UNSET)

        def _parse_last_fired_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        last_fired_at = _parse_last_fired_at(d.pop("last_fired_at", UNSET))


        def _parse_next_fire_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        next_fire_at = _parse_next_fire_at(d.pop("next_fire_at", UNSET))


        schedule_read = cls(
            created_at=created_at,
            cron_expr=cron_expr,
            id=id,
            name=name,
            template_type=template_type,
            updated_at=updated_at,
            context=context,
            enabled=enabled,
            last_fired_at=last_fired_at,
            next_fire_at=next_fire_at,
        )


        schedule_read.additional_properties = d
        return schedule_read

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
