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
  from ..models.template_update_quiet_hours_type_0 import TemplateUpdateQuietHoursType0





T = TypeVar("T", bound="TemplateUpdate")



@_attrs_define
class TemplateUpdate:
    """ 
        Attributes:
            category (None | str | Unset):
            description (None | str | Unset):
            enabled (bool | None | Unset):
            gate_min (float | None | Unset): Threshold for `gate_variable` (deliver while value ≥ gate_min).
            gate_variable (None | str | Unset): Variable the delivery gate reads. With `gate_min`: the alert is suppressed
                (`below_gate`) while this variable is below `gate_min`. A missing, stale or non-numeric value never suppresses
                (fail-open).
            icon (None | str | Unset):
            locale (None | str | Unset):
            message_template (None | str | Unset):
            min_repeat_min (int | None | Unset):
            quiet_hours (None | TemplateUpdateQuietHoursType0 | Unset):
            require_pv_kw (float | None | Unset): Deprecated alias of `gate_min` (pre-0030 name). Removed in /v2.
            runbook_url (None | str | Unset):
            severity (None | Severity | Unset):
            title_template (None | str | Unset):
     """

    category: None | str | Unset = UNSET
    description: None | str | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    gate_min: float | None | Unset = UNSET
    gate_variable: None | str | Unset = UNSET
    icon: None | str | Unset = UNSET
    locale: None | str | Unset = UNSET
    message_template: None | str | Unset = UNSET
    min_repeat_min: int | None | Unset = UNSET
    quiet_hours: None | TemplateUpdateQuietHoursType0 | Unset = UNSET
    require_pv_kw: float | None | Unset = UNSET
    runbook_url: None | str | Unset = UNSET
    severity: None | Severity | Unset = UNSET
    title_template: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.template_update_quiet_hours_type_0 import TemplateUpdateQuietHoursType0 # noqa: PLC0415
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

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
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

        locale: None | str | Unset
        if isinstance(self.locale, Unset):
            locale = UNSET
        else:
            locale = self.locale

        message_template: None | str | Unset
        if isinstance(self.message_template, Unset):
            message_template = UNSET
        else:
            message_template = self.message_template

        min_repeat_min: int | None | Unset
        if isinstance(self.min_repeat_min, Unset):
            min_repeat_min = UNSET
        else:
            min_repeat_min = self.min_repeat_min

        quiet_hours: dict[str, Any] | None | Unset
        if isinstance(self.quiet_hours, Unset):
            quiet_hours = UNSET
        elif isinstance(self.quiet_hours, TemplateUpdateQuietHoursType0):
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

        severity: None | str | Unset
        if isinstance(self.severity, Unset):
            severity = UNSET
        elif isinstance(self.severity, Severity):
            severity = self.severity.value
        else:
            severity = self.severity

        title_template: None | str | Unset
        if isinstance(self.title_template, Unset):
            title_template = UNSET
        else:
            title_template = self.title_template


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
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
        if severity is not UNSET:
            field_dict["severity"] = severity
        if title_template is not UNSET:
            field_dict["title_template"] = title_template

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.template_update_quiet_hours_type_0 import TemplateUpdateQuietHoursType0 # noqa: PLC0415
        d = dict(src_dict)
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


        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))


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


        def _parse_locale(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        locale = _parse_locale(d.pop("locale", UNSET))


        def _parse_message_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message_template = _parse_message_template(d.pop("message_template", UNSET))


        def _parse_min_repeat_min(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        min_repeat_min = _parse_min_repeat_min(d.pop("min_repeat_min", UNSET))


        def _parse_quiet_hours(data: object) -> None | TemplateUpdateQuietHoursType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                quiet_hours_type_0 = TemplateUpdateQuietHoursType0.from_dict(data)



                return quiet_hours_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateUpdateQuietHoursType0 | Unset, data)

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


        def _parse_severity(data: object) -> None | Severity | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                severity_type_0 = Severity(data)



                return severity_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Severity | Unset, data)

        severity = _parse_severity(d.pop("severity", UNSET))


        def _parse_title_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title_template = _parse_title_template(d.pop("title_template", UNSET))


        template_update = cls(
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
            severity=severity,
            title_template=title_template,
        )


        template_update.additional_properties = d
        return template_update

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
