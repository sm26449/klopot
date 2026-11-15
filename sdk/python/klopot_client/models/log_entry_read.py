from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.log_entry_read_failed_channels import LogEntryReadFailedChannels
  from ..models.log_entry_read_vars_payload_type_0 import LogEntryReadVarsPayloadType0





T = TypeVar("T", bound="LogEntryRead")



@_attrs_define
class LogEntryRead:
    """ Read shape for a ``notifications_log`` row.

        Attributes:
            dispatched_to (list[str]):
            failed_channels (LogEntryReadFailedChannels):
            fired_at (None | str):
            id (str):
            severity (str):
            title (str):
            type_ (str):
            acknowledged_at (None | str | Unset):
            acknowledged_by (None | str | Unset):
            delivery_status (None | str | Unset):
            dispatch_latency_ms (int | None | Unset):
            escalated_at (None | str | Unset):
            incident_event (None | str | Unset):
            incident_id (None | str | Unset):
            is_test (bool | Unset):  Default: False.
            message (None | str | Unset):
            rule_id (int | None | Unset):
            snoozed_until (None | str | Unset):
            source (None | str | Unset):
            suppressed_reason (None | str | Unset):
            template_id (int | None | Unset):
            trace_id (None | str | Unset):
            vars_payload (LogEntryReadVarsPayloadType0 | None | Unset):
     """

    dispatched_to: list[str]
    failed_channels: LogEntryReadFailedChannels
    fired_at: None | str
    id: str
    severity: str
    title: str
    type_: str
    acknowledged_at: None | str | Unset = UNSET
    acknowledged_by: None | str | Unset = UNSET
    delivery_status: None | str | Unset = UNSET
    dispatch_latency_ms: int | None | Unset = UNSET
    escalated_at: None | str | Unset = UNSET
    incident_event: None | str | Unset = UNSET
    incident_id: None | str | Unset = UNSET
    is_test: bool | Unset = False
    message: None | str | Unset = UNSET
    rule_id: int | None | Unset = UNSET
    snoozed_until: None | str | Unset = UNSET
    source: None | str | Unset = UNSET
    suppressed_reason: None | str | Unset = UNSET
    template_id: int | None | Unset = UNSET
    trace_id: None | str | Unset = UNSET
    vars_payload: LogEntryReadVarsPayloadType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.log_entry_read_failed_channels import LogEntryReadFailedChannels # noqa: PLC0415
        from ..models.log_entry_read_vars_payload_type_0 import LogEntryReadVarsPayloadType0 # noqa: PLC0415
        dispatched_to = self.dispatched_to



        failed_channels = self.failed_channels.to_dict()

        fired_at: None | str
        fired_at = self.fired_at

        id = self.id

        severity = self.severity

        title = self.title

        type_ = self.type_

        acknowledged_at: None | str | Unset
        if isinstance(self.acknowledged_at, Unset):
            acknowledged_at = UNSET
        else:
            acknowledged_at = self.acknowledged_at

        acknowledged_by: None | str | Unset
        if isinstance(self.acknowledged_by, Unset):
            acknowledged_by = UNSET
        else:
            acknowledged_by = self.acknowledged_by

        delivery_status: None | str | Unset
        if isinstance(self.delivery_status, Unset):
            delivery_status = UNSET
        else:
            delivery_status = self.delivery_status

        dispatch_latency_ms: int | None | Unset
        if isinstance(self.dispatch_latency_ms, Unset):
            dispatch_latency_ms = UNSET
        else:
            dispatch_latency_ms = self.dispatch_latency_ms

        escalated_at: None | str | Unset
        if isinstance(self.escalated_at, Unset):
            escalated_at = UNSET
        else:
            escalated_at = self.escalated_at

        incident_event: None | str | Unset
        if isinstance(self.incident_event, Unset):
            incident_event = UNSET
        else:
            incident_event = self.incident_event

        incident_id: None | str | Unset
        if isinstance(self.incident_id, Unset):
            incident_id = UNSET
        else:
            incident_id = self.incident_id

        is_test = self.is_test

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        rule_id: int | None | Unset
        if isinstance(self.rule_id, Unset):
            rule_id = UNSET
        else:
            rule_id = self.rule_id

        snoozed_until: None | str | Unset
        if isinstance(self.snoozed_until, Unset):
            snoozed_until = UNSET
        else:
            snoozed_until = self.snoozed_until

        source: None | str | Unset
        if isinstance(self.source, Unset):
            source = UNSET
        else:
            source = self.source

        suppressed_reason: None | str | Unset
        if isinstance(self.suppressed_reason, Unset):
            suppressed_reason = UNSET
        else:
            suppressed_reason = self.suppressed_reason

        template_id: int | None | Unset
        if isinstance(self.template_id, Unset):
            template_id = UNSET
        else:
            template_id = self.template_id

        trace_id: None | str | Unset
        if isinstance(self.trace_id, Unset):
            trace_id = UNSET
        else:
            trace_id = self.trace_id

        vars_payload: dict[str, Any] | None | Unset
        if isinstance(self.vars_payload, Unset):
            vars_payload = UNSET
        elif isinstance(self.vars_payload, LogEntryReadVarsPayloadType0):
            vars_payload = self.vars_payload.to_dict()
        else:
            vars_payload = self.vars_payload


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "dispatched_to": dispatched_to,
            "failed_channels": failed_channels,
            "fired_at": fired_at,
            "id": id,
            "severity": severity,
            "title": title,
            "type": type_,
        })
        if acknowledged_at is not UNSET:
            field_dict["acknowledged_at"] = acknowledged_at
        if acknowledged_by is not UNSET:
            field_dict["acknowledged_by"] = acknowledged_by
        if delivery_status is not UNSET:
            field_dict["delivery_status"] = delivery_status
        if dispatch_latency_ms is not UNSET:
            field_dict["dispatch_latency_ms"] = dispatch_latency_ms
        if escalated_at is not UNSET:
            field_dict["escalated_at"] = escalated_at
        if incident_event is not UNSET:
            field_dict["incident_event"] = incident_event
        if incident_id is not UNSET:
            field_dict["incident_id"] = incident_id
        if is_test is not UNSET:
            field_dict["is_test"] = is_test
        if message is not UNSET:
            field_dict["message"] = message
        if rule_id is not UNSET:
            field_dict["rule_id"] = rule_id
        if snoozed_until is not UNSET:
            field_dict["snoozed_until"] = snoozed_until
        if source is not UNSET:
            field_dict["source"] = source
        if suppressed_reason is not UNSET:
            field_dict["suppressed_reason"] = suppressed_reason
        if template_id is not UNSET:
            field_dict["template_id"] = template_id
        if trace_id is not UNSET:
            field_dict["trace_id"] = trace_id
        if vars_payload is not UNSET:
            field_dict["vars_payload"] = vars_payload

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.log_entry_read_failed_channels import LogEntryReadFailedChannels # noqa: PLC0415
        from ..models.log_entry_read_vars_payload_type_0 import LogEntryReadVarsPayloadType0 # noqa: PLC0415
        d = dict(src_dict)
        dispatched_to = cast(list[str], d.pop("dispatched_to"))


        failed_channels = LogEntryReadFailedChannels.from_dict(d.pop("failed_channels"))




        def _parse_fired_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        fired_at = _parse_fired_at(d.pop("fired_at"))


        id = d.pop("id")

        severity = d.pop("severity")

        title = d.pop("title")

        type_ = d.pop("type")

        def _parse_acknowledged_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        acknowledged_at = _parse_acknowledged_at(d.pop("acknowledged_at", UNSET))


        def _parse_acknowledged_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        acknowledged_by = _parse_acknowledged_by(d.pop("acknowledged_by", UNSET))


        def _parse_delivery_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        delivery_status = _parse_delivery_status(d.pop("delivery_status", UNSET))


        def _parse_dispatch_latency_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        dispatch_latency_ms = _parse_dispatch_latency_ms(d.pop("dispatch_latency_ms", UNSET))


        def _parse_escalated_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        escalated_at = _parse_escalated_at(d.pop("escalated_at", UNSET))


        def _parse_incident_event(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        incident_event = _parse_incident_event(d.pop("incident_event", UNSET))


        def _parse_incident_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        incident_id = _parse_incident_id(d.pop("incident_id", UNSET))


        is_test = d.pop("is_test", UNSET)

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))


        def _parse_rule_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        rule_id = _parse_rule_id(d.pop("rule_id", UNSET))


        def _parse_snoozed_until(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        snoozed_until = _parse_snoozed_until(d.pop("snoozed_until", UNSET))


        def _parse_source(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source = _parse_source(d.pop("source", UNSET))


        def _parse_suppressed_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        suppressed_reason = _parse_suppressed_reason(d.pop("suppressed_reason", UNSET))


        def _parse_template_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        template_id = _parse_template_id(d.pop("template_id", UNSET))


        def _parse_trace_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trace_id = _parse_trace_id(d.pop("trace_id", UNSET))


        def _parse_vars_payload(data: object) -> LogEntryReadVarsPayloadType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                vars_payload_type_0 = LogEntryReadVarsPayloadType0.from_dict(data)



                return vars_payload_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LogEntryReadVarsPayloadType0 | None | Unset, data)

        vars_payload = _parse_vars_payload(d.pop("vars_payload", UNSET))


        log_entry_read = cls(
            dispatched_to=dispatched_to,
            failed_channels=failed_channels,
            fired_at=fired_at,
            id=id,
            severity=severity,
            title=title,
            type_=type_,
            acknowledged_at=acknowledged_at,
            acknowledged_by=acknowledged_by,
            delivery_status=delivery_status,
            dispatch_latency_ms=dispatch_latency_ms,
            escalated_at=escalated_at,
            incident_event=incident_event,
            incident_id=incident_id,
            is_test=is_test,
            message=message,
            rule_id=rule_id,
            snoozed_until=snoozed_until,
            source=source,
            suppressed_reason=suppressed_reason,
            template_id=template_id,
            trace_id=trace_id,
            vars_payload=vars_payload,
        )


        log_entry_read.additional_properties = d
        return log_entry_read

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
