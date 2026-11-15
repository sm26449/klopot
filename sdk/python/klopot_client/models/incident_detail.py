from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.incident_detail_state import IncidentDetailState
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.incident_detail_opening_context import IncidentDetailOpeningContext
  from ..models.incident_detail_resolution_context_type_0 import IncidentDetailResolutionContextType0





T = TypeVar("T", bound="IncidentDetail")



@_attrs_define
class IncidentDetail:
    """ 
        Attributes:
            acknowledged_at (None | str):
            acknowledged_by (None | str):
            duration_sec (int):
            id (str):
            opened_at (None | str):
            opening_context (IncidentDetailOpeningContext):
            resolution_context (IncidentDetailResolutionContextType0 | None):
            resolution_reason (None | str):
            resolved_at (None | str):
            resolved_template_type (None | str):
            rule_id (int | None):
            rule_name (str):
            severity (str):
            state (IncidentDetailState):
            template_type (str):
            title (str):
            source_key (None | str | Unset):
            source_kind (str | Unset):  Default: 'rule'.
     """

    acknowledged_at: None | str
    acknowledged_by: None | str
    duration_sec: int
    id: str
    opened_at: None | str
    opening_context: IncidentDetailOpeningContext
    resolution_context: IncidentDetailResolutionContextType0 | None
    resolution_reason: None | str
    resolved_at: None | str
    resolved_template_type: None | str
    rule_id: int | None
    rule_name: str
    severity: str
    state: IncidentDetailState
    template_type: str
    title: str
    source_key: None | str | Unset = UNSET
    source_kind: str | Unset = 'rule'
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.incident_detail_opening_context import IncidentDetailOpeningContext # noqa: PLC0415
        from ..models.incident_detail_resolution_context_type_0 import IncidentDetailResolutionContextType0 # noqa: PLC0415
        acknowledged_at: None | str
        acknowledged_at = self.acknowledged_at

        acknowledged_by: None | str
        acknowledged_by = self.acknowledged_by

        duration_sec = self.duration_sec

        id = self.id

        opened_at: None | str
        opened_at = self.opened_at

        opening_context = self.opening_context.to_dict()

        resolution_context: dict[str, Any] | None
        if isinstance(self.resolution_context, IncidentDetailResolutionContextType0):
            resolution_context = self.resolution_context.to_dict()
        else:
            resolution_context = self.resolution_context

        resolution_reason: None | str
        resolution_reason = self.resolution_reason

        resolved_at: None | str
        resolved_at = self.resolved_at

        resolved_template_type: None | str
        resolved_template_type = self.resolved_template_type

        rule_id: int | None
        rule_id = self.rule_id

        rule_name = self.rule_name

        severity = self.severity

        state = self.state.value

        template_type = self.template_type

        title = self.title

        source_key: None | str | Unset
        if isinstance(self.source_key, Unset):
            source_key = UNSET
        else:
            source_key = self.source_key

        source_kind = self.source_kind


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "acknowledged_at": acknowledged_at,
            "acknowledged_by": acknowledged_by,
            "duration_sec": duration_sec,
            "id": id,
            "opened_at": opened_at,
            "opening_context": opening_context,
            "resolution_context": resolution_context,
            "resolution_reason": resolution_reason,
            "resolved_at": resolved_at,
            "resolved_template_type": resolved_template_type,
            "rule_id": rule_id,
            "rule_name": rule_name,
            "severity": severity,
            "state": state,
            "template_type": template_type,
            "title": title,
        })
        if source_key is not UNSET:
            field_dict["source_key"] = source_key
        if source_kind is not UNSET:
            field_dict["source_kind"] = source_kind

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.incident_detail_opening_context import IncidentDetailOpeningContext # noqa: PLC0415
        from ..models.incident_detail_resolution_context_type_0 import IncidentDetailResolutionContextType0 # noqa: PLC0415
        d = dict(src_dict)
        def _parse_acknowledged_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        acknowledged_at = _parse_acknowledged_at(d.pop("acknowledged_at"))


        def _parse_acknowledged_by(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        acknowledged_by = _parse_acknowledged_by(d.pop("acknowledged_by"))


        duration_sec = d.pop("duration_sec")

        id = d.pop("id")

        def _parse_opened_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        opened_at = _parse_opened_at(d.pop("opened_at"))


        opening_context = IncidentDetailOpeningContext.from_dict(d.pop("opening_context"))




        def _parse_resolution_context(data: object) -> IncidentDetailResolutionContextType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                resolution_context_type_0 = IncidentDetailResolutionContextType0.from_dict(data)



                return resolution_context_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IncidentDetailResolutionContextType0 | None, data)

        resolution_context = _parse_resolution_context(d.pop("resolution_context"))


        def _parse_resolution_reason(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        resolution_reason = _parse_resolution_reason(d.pop("resolution_reason"))


        def _parse_resolved_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        resolved_at = _parse_resolved_at(d.pop("resolved_at"))


        def _parse_resolved_template_type(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        resolved_template_type = _parse_resolved_template_type(d.pop("resolved_template_type"))


        def _parse_rule_id(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        rule_id = _parse_rule_id(d.pop("rule_id"))


        rule_name = d.pop("rule_name")

        severity = d.pop("severity")

        state = IncidentDetailState(d.pop("state"))




        template_type = d.pop("template_type")

        title = d.pop("title")

        def _parse_source_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source_key = _parse_source_key(d.pop("source_key", UNSET))


        source_kind = d.pop("source_kind", UNSET)

        incident_detail = cls(
            acknowledged_at=acknowledged_at,
            acknowledged_by=acknowledged_by,
            duration_sec=duration_sec,
            id=id,
            opened_at=opened_at,
            opening_context=opening_context,
            resolution_context=resolution_context,
            resolution_reason=resolution_reason,
            resolved_at=resolved_at,
            resolved_template_type=resolved_template_type,
            rule_id=rule_id,
            rule_name=rule_name,
            severity=severity,
            state=state,
            template_type=template_type,
            title=title,
            source_key=source_key,
            source_kind=source_kind,
        )


        incident_detail.additional_properties = d
        return incident_detail

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
