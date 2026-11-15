from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.schedule_update_context_type_0 import ScheduleUpdateContextType0





T = TypeVar("T", bound="ScheduleUpdate")



@_attrs_define
class ScheduleUpdate:
    """ 
        Attributes:
            context (None | ScheduleUpdateContextType0 | Unset):
            cron_expr (None | str | Unset):
            enabled (bool | None | Unset):
            template_type (None | str | Unset):
     """

    context: None | ScheduleUpdateContextType0 | Unset = UNSET
    cron_expr: None | str | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    template_type: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.schedule_update_context_type_0 import ScheduleUpdateContextType0 # noqa: PLC0415
        context: dict[str, Any] | None | Unset
        if isinstance(self.context, Unset):
            context = UNSET
        elif isinstance(self.context, ScheduleUpdateContextType0):
            context = self.context.to_dict()
        else:
            context = self.context

        cron_expr: None | str | Unset
        if isinstance(self.cron_expr, Unset):
            cron_expr = UNSET
        else:
            cron_expr = self.cron_expr

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        template_type: None | str | Unset
        if isinstance(self.template_type, Unset):
            template_type = UNSET
        else:
            template_type = self.template_type


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if context is not UNSET:
            field_dict["context"] = context
        if cron_expr is not UNSET:
            field_dict["cron_expr"] = cron_expr
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if template_type is not UNSET:
            field_dict["template_type"] = template_type

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.schedule_update_context_type_0 import ScheduleUpdateContextType0 # noqa: PLC0415
        d = dict(src_dict)
        def _parse_context(data: object) -> None | ScheduleUpdateContextType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                context_type_0 = ScheduleUpdateContextType0.from_dict(data)



                return context_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ScheduleUpdateContextType0 | Unset, data)

        context = _parse_context(d.pop("context", UNSET))


        def _parse_cron_expr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cron_expr = _parse_cron_expr(d.pop("cron_expr", UNSET))


        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))


        def _parse_template_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        template_type = _parse_template_type(d.pop("template_type", UNSET))


        schedule_update = cls(
            context=context,
            cron_expr=cron_expr,
            enabled=enabled,
            template_type=template_type,
        )


        schedule_update.additional_properties = d
        return schedule_update

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
