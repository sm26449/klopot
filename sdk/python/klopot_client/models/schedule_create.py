from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.schedule_create_context import ScheduleCreateContext





T = TypeVar("T", bound="ScheduleCreate")



@_attrs_define
class ScheduleCreate:
    """ 
        Attributes:
            cron_expr (str):
            name (str):
            template_type (str):
            context (ScheduleCreateContext | Unset):
            enabled (bool | Unset):  Default: True.
     """

    cron_expr: str
    name: str
    template_type: str
    context: ScheduleCreateContext | Unset = UNSET
    enabled: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.schedule_create_context import ScheduleCreateContext # noqa: PLC0415
        cron_expr = self.cron_expr

        name = self.name

        template_type = self.template_type

        context: dict[str, Any] | Unset = UNSET
        if not isinstance(self.context, Unset):
            context = self.context.to_dict()

        enabled = self.enabled


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "cron_expr": cron_expr,
            "name": name,
            "template_type": template_type,
        })
        if context is not UNSET:
            field_dict["context"] = context
        if enabled is not UNSET:
            field_dict["enabled"] = enabled

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.schedule_create_context import ScheduleCreateContext # noqa: PLC0415
        d = dict(src_dict)
        cron_expr = d.pop("cron_expr")

        name = d.pop("name")

        template_type = d.pop("template_type")

        _context = d.pop("context", UNSET)
        context: ScheduleCreateContext | Unset
        if isinstance(_context,  Unset):
            context = UNSET
        else:
            context = ScheduleCreateContext.from_dict(_context)




        enabled = d.pop("enabled", UNSET)

        schedule_create = cls(
            cron_expr=cron_expr,
            name=name,
            template_type=template_type,
            context=context,
            enabled=enabled,
        )


        schedule_create.additional_properties = d
        return schedule_create

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
