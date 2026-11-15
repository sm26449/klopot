from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.severity import Severity
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.template_read_quiet_hours_type_0 import TemplateReadQuietHoursType0





T = TypeVar("T", bound="TemplateRead")



@_attrs_define
class TemplateRead:
    """ 
        Attributes:
            created_at (None | str):
            id (int):
            severity (Severity):
            title_template (str):
            type_ (str):
            updated_at (None | str):
            category (None | str | Unset):
            description (None | str | Unset):
            enabled (bool | Unset):  Default: True.
            gate_min (float | None | Unset): Threshold for `gate_variable` (deliver while value ≥ gate_min).
            gate_variable (None | str | Unset): Variable the delivery gate reads. With `gate_min`: the alert is suppressed
                (`below_gate`) while this variable is below `gate_min`. A missing, stale or non-numeric value never suppresses
                (fail-open).
            icon (None | str | Unset):
            locale (str | Unset):  Default: 'en'.
            message_template (None | str | Unset):
            min_repeat_min (int | Unset):  Default: 30.
            quiet_hours (None | TemplateReadQuietHoursType0 | Unset):
            require_pv_kw (float | None | Unset): Deprecated alias of `gate_min` (pre-0030 name). Removed in /v2.
            runbook_url (None | str | Unset):
     """

    created_at: None | str
    id: int
    severity: Severity
    title_template: str
    type_: str
    updated_at: None | str
    category: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    enabled: bool | Unset = True
    gate_min: float | None | Unset = UNSET
    gate_variable: None | str | Unset = UNSET
    icon: None | str | Unset = UNSET
    locale: str | Unset = 'en'
    message_template: None | str | Unset = UNSET
    min_repeat_min: int | Unset = 30
    quiet_hours: None | TemplateReadQuietHoursType0 | Unset = UNSET
    require_pv_kw: float | None | Unset = UNSET
    runbook_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.template_read_quiet_hours_type_0 import TemplateReadQuietHoursType0 # noqa: PLC0415
        created_at: None | str
        created_at = self.created_at

        id = self.id

        severity = self.severity.value

        title_template = self.title_template

        type_ = self.type_

        updated_at: None | str
        updated_at = self.updated_at

        category: None | str | Unset
        if isinstance(self.category, Unset):
            category = UNSET
        else:
            category = self.category

        description: None | str | Unset
        if isinstance(self.description, Unset):
            description = UNSET
        else:
            description = self.description

        enabled = self.enabled

        gate_min: float | None | Unset
        if isinstance(self.gate_min, Unset):
            gate_min = UNSET
        else:
            gate_min = self.gate_min

        gate_variable: None | str | Unset
        if isinstance(self.gate_variable, Unset):
            gate_variable = UNSET
        else:
            gate_variable = self.gate_variable

        icon: None | str | Unset
        if isinstance(self.icon, Unset):
            icon = UNSET
        else:
            icon = self.icon

        locale = self.locale

        message_template: None | str | Unset
        if isinstance(self.message_template, Unset):
            message_template = UNSET
        else:
            message_template = self.message_template

        min_repeat_min = self.min_repeat_min

        quiet_hours: dict[str, Any] | None | Unset
        if isinstance(self.quiet_hours, Unset):
            quiet_hours = UNSET
        elif isinstance(self.quiet_hours, TemplateReadQuietHoursType0):
            quiet_hours = self.quiet_hours.to_dict()
        else:
            quiet_hours = self.quiet_hours

        require_pv_kw: float | None | Unset
        if isinstance(self.require_pv_kw, Unset):
            require_pv_kw = UNSET
        else:
            require_pv_kw = self.require_pv_kw

        runbook_url: None | str | Unset
        if isinstance(self.runbook_url, Unset):
            runbook_url = UNSET
        else:
            runbook_url = self.runbook_url


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "id": id,
            "severity": severity,
            "title_template": title_template,
            "type": type_,
            "updated_at": updated_at,
        })
        if category is not UNSET:
            field_dict["category"] = category
        if description is not UNSET:
            field_dict["description"] = description
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if gate_min is not UNSET:
            field_dict["gate_min"] = gate_min
        if gate_variable is not UNSET:
            field_dict["gate_variable"] = gate_variable
        if icon is not UNSET:
            field_dict["icon"] = icon
        if locale is not UNSET:
            field_dict["locale"] = locale
        if message_template is not UNSET:
            field_dict["message_template"] = message_template
        if min_repeat_min is not UNSET:
            field_dict["min_repeat_min"] = min_repeat_min
        if quiet_hours is not UNSET:
            field_dict["quiet_hours"] = quiet_hours
        if require_pv_kw is not UNSET:
            field_dict["require_pv_kw"] = require_pv_kw
        if runbook_url is not UNSET:
            field_dict["runbook_url"] = runbook_url

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.template_read_quiet_hours_type_0 import TemplateReadQuietHoursType0 # noqa: PLC0415
        d = dict(src_dict)
        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        id = d.pop("id")

        severity = Severity(d.pop("severity"))




        title_template = d.pop("title_template")

        type_ = d.pop("type")

        def _parse_updated_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))


        def _parse_category(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        category = _parse_category(d.pop("category", UNSET))


        def _parse_description(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        description = _parse_description(d.pop("description", UNSET))


        enabled = d.pop("enabled", UNSET)

        def _parse_gate_min(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        gate_min = _parse_gate_min(d.pop("gate_min", UNSET))


        def _parse_gate_variable(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        gate_variable = _parse_gate_variable(d.pop("gate_variable", UNSET))


        def _parse_icon(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        icon = _parse_icon(d.pop("icon", UNSET))


        locale = d.pop("locale", UNSET)

        def _parse_message_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message_template = _parse_message_template(d.pop("message_template", UNSET))


        min_repeat_min = d.pop("min_repeat_min", UNSET)

        def _parse_quiet_hours(data: object) -> None | TemplateReadQuietHoursType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                quiet_hours_type_0 = TemplateReadQuietHoursType0.from_dict(data)



                return quiet_hours_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateReadQuietHoursType0 | Unset, data)

        quiet_hours = _parse_quiet_hours(d.pop("quiet_hours", UNSET))


        def _parse_require_pv_kw(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        require_pv_kw = _parse_require_pv_kw(d.pop("require_pv_kw", UNSET))


        def _parse_runbook_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        runbook_url = _parse_runbook_url(d.pop("runbook_url", UNSET))


        template_read = cls(
            created_at=created_at,
            id=id,
            severity=severity,
            title_template=title_template,
            type_=type_,
            updated_at=updated_at,
            category=category,
            description=description,
            enabled=enabled,
            gate_min=gate_min,
            gate_variable=gate_variable,
            icon=icon,
            locale=locale,
            message_template=message_template,
            min_repeat_min=min_repeat_min,
            quiet_hours=quiet_hours,
            require_pv_kw=require_pv_kw,
            runbook_url=runbook_url,
        )


        template_read.additional_properties = d
        return template_read

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
