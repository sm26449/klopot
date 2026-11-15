from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.audit_log_read_after_type_0 import AuditLogReadAfterType0
  from ..models.audit_log_read_before_type_0 import AuditLogReadBeforeType0





T = TypeVar("T", bound="AuditLogRead")



@_attrs_define
class AuditLogRead:
    """ Read shape for an ``audit_log`` row.

    Populated by ``record_change()`` on every CRUD touching a
    resource. ``before`` / ``after`` are JSON snapshots — operators
    use the diff to see exactly what changed.

    ``ts`` is naive UTC at rest (audit #121, v1.3.4); the Pydantic
    serializer emits a Z-suffixed ISO so the UI can convert to the
    operator's local time unambiguously.

        Attributes:
            action (str):
            actor_kind (str):
            id (int):
            ts (None | str):
            actor_id (int | None | Unset):
            actor_name (None | str | Unset):
            after (AuditLogReadAfterType0 | None | Unset):
            before (AuditLogReadBeforeType0 | None | Unset):
            resource_id (None | str | Unset):
            resource_kind (None | str | Unset):
            trace_id (None | str | Unset):
     """

    action: str
    actor_kind: str
    id: int
    ts: None | str
    actor_id: int | None | Unset = UNSET
    actor_name: None | str | Unset = UNSET
    after: AuditLogReadAfterType0 | None | Unset = UNSET
    before: AuditLogReadBeforeType0 | None | Unset = UNSET
    resource_id: None | str | Unset = UNSET
    resource_kind: None | str | Unset = UNSET
    trace_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.audit_log_read_after_type_0 import AuditLogReadAfterType0 # noqa: PLC0415
        from ..models.audit_log_read_before_type_0 import AuditLogReadBeforeType0 # noqa: PLC0415
        action = self.action

        actor_kind = self.actor_kind

        id = self.id

        ts: None | str
        ts = self.ts

        actor_id: int | None | Unset
        if isinstance(self.actor_id, Unset):
            actor_id = UNSET
        else:
            actor_id = self.actor_id

        actor_name: None | str | Unset
        if isinstance(self.actor_name, Unset):
            actor_name = UNSET
        else:
            actor_name = self.actor_name

        after: dict[str, Any] | None | Unset
        if isinstance(self.after, Unset):
            after = UNSET
        elif isinstance(self.after, AuditLogReadAfterType0):
            after = self.after.to_dict()
        else:
            after = self.after

        before: dict[str, Any] | None | Unset
        if isinstance(self.before, Unset):
            before = UNSET
        elif isinstance(self.before, AuditLogReadBeforeType0):
            before = self.before.to_dict()
        else:
            before = self.before

        resource_id: None | str | Unset
        if isinstance(self.resource_id, Unset):
            resource_id = UNSET
        else:
            resource_id = self.resource_id

        resource_kind: None | str | Unset
        if isinstance(self.resource_kind, Unset):
            resource_kind = UNSET
        else:
            resource_kind = self.resource_kind

        trace_id: None | str | Unset
        if isinstance(self.trace_id, Unset):
            trace_id = UNSET
        else:
            trace_id = self.trace_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "action": action,
            "actor_kind": actor_kind,
            "id": id,
            "ts": ts,
        })
        if actor_id is not UNSET:
            field_dict["actor_id"] = actor_id
        if actor_name is not UNSET:
            field_dict["actor_name"] = actor_name
        if after is not UNSET:
            field_dict["after"] = after
        if before is not UNSET:
            field_dict["before"] = before
        if resource_id is not UNSET:
            field_dict["resource_id"] = resource_id
        if resource_kind is not UNSET:
            field_dict["resource_kind"] = resource_kind
        if trace_id is not UNSET:
            field_dict["trace_id"] = trace_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.audit_log_read_after_type_0 import AuditLogReadAfterType0 # noqa: PLC0415
        from ..models.audit_log_read_before_type_0 import AuditLogReadBeforeType0 # noqa: PLC0415
        d = dict(src_dict)
        action = d.pop("action")

        actor_kind = d.pop("actor_kind")

        id = d.pop("id")

        def _parse_ts(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        ts = _parse_ts(d.pop("ts"))


        def _parse_actor_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        actor_id = _parse_actor_id(d.pop("actor_id", UNSET))


        def _parse_actor_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        actor_name = _parse_actor_name(d.pop("actor_name", UNSET))


        def _parse_after(data: object) -> AuditLogReadAfterType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                after_type_0 = AuditLogReadAfterType0.from_dict(data)



                return after_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AuditLogReadAfterType0 | None | Unset, data)

        after = _parse_after(d.pop("after", UNSET))


        def _parse_before(data: object) -> AuditLogReadBeforeType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                before_type_0 = AuditLogReadBeforeType0.from_dict(data)



                return before_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(AuditLogReadBeforeType0 | None | Unset, data)

        before = _parse_before(d.pop("before", UNSET))


        def _parse_resource_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resource_id = _parse_resource_id(d.pop("resource_id", UNSET))


        def _parse_resource_kind(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resource_kind = _parse_resource_kind(d.pop("resource_kind", UNSET))


        def _parse_trace_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trace_id = _parse_trace_id(d.pop("trace_id", UNSET))


        audit_log_read = cls(
            action=action,
            actor_kind=actor_kind,
            id=id,
            ts=ts,
            actor_id=actor_id,
            actor_name=actor_name,
            after=after,
            before=before,
            resource_id=resource_id,
            resource_kind=resource_kind,
            trace_id=trace_id,
        )


        audit_log_read.additional_properties = d
        return audit_log_read

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
