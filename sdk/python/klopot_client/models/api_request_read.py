from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="ApiRequestRead")



@_attrs_define
class ApiRequestRead:
    """ 
        Attributes:
            duration_ms (Any):
            expires_at (Any):
            id (Any):
            method (Any):
            path (Any):
            route (Any):
            status (Any):
            ts (Any):
            actor_kind (Any | Unset):
            actor_name (Any | Unset):
            api_key_id (Any | Unset):
            client_ip (Any | Unset):
            has_request_body (Any | Unset):
            has_response_body (Any | Unset):
            rule_id (Any | Unset):
            trace_id (Any | Unset):
            user_agent (Any | Unset):
     """

    duration_ms: Any
    expires_at: Any
    id: Any
    method: Any
    path: Any
    route: Any
    status: Any
    ts: Any
    actor_kind: Any | Unset = UNSET
    actor_name: Any | Unset = UNSET
    api_key_id: Any | Unset = UNSET
    client_ip: Any | Unset = UNSET
    has_request_body: Any | Unset = UNSET
    has_response_body: Any | Unset = UNSET
    rule_id: Any | Unset = UNSET
    trace_id: Any | Unset = UNSET
    user_agent: Any | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        duration_ms = self.duration_ms

        expires_at = self.expires_at

        id = self.id

        method = self.method

        path = self.path

        route = self.route

        status = self.status

        ts = self.ts

        actor_kind = self.actor_kind

        actor_name = self.actor_name

        api_key_id = self.api_key_id

        client_ip = self.client_ip

        has_request_body = self.has_request_body

        has_response_body = self.has_response_body

        rule_id = self.rule_id

        trace_id = self.trace_id

        user_agent = self.user_agent


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "duration_ms": duration_ms,
            "expires_at": expires_at,
            "id": id,
            "method": method,
            "path": path,
            "route": route,
            "status": status,
            "ts": ts,
        })
        if actor_kind is not UNSET:
            field_dict["actor_kind"] = actor_kind
        if actor_name is not UNSET:
            field_dict["actor_name"] = actor_name
        if api_key_id is not UNSET:
            field_dict["api_key_id"] = api_key_id
        if client_ip is not UNSET:
            field_dict["client_ip"] = client_ip
        if has_request_body is not UNSET:
            field_dict["has_request_body"] = has_request_body
        if has_response_body is not UNSET:
            field_dict["has_response_body"] = has_response_body
        if rule_id is not UNSET:
            field_dict["rule_id"] = rule_id
        if trace_id is not UNSET:
            field_dict["trace_id"] = trace_id
        if user_agent is not UNSET:
            field_dict["user_agent"] = user_agent

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        duration_ms = d.pop("duration_ms")

        expires_at = d.pop("expires_at")

        id = d.pop("id")

        method = d.pop("method")

        path = d.pop("path")

        route = d.pop("route")

        status = d.pop("status")

        ts = d.pop("ts")

        actor_kind = d.pop("actor_kind", UNSET)

        actor_name = d.pop("actor_name", UNSET)

        api_key_id = d.pop("api_key_id", UNSET)

        client_ip = d.pop("client_ip", UNSET)

        has_request_body = d.pop("has_request_body", UNSET)

        has_response_body = d.pop("has_response_body", UNSET)

        rule_id = d.pop("rule_id", UNSET)

        trace_id = d.pop("trace_id", UNSET)

        user_agent = d.pop("user_agent", UNSET)

        api_request_read = cls(
            duration_ms=duration_ms,
            expires_at=expires_at,
            id=id,
            method=method,
            path=path,
            route=route,
            status=status,
            ts=ts,
            actor_kind=actor_kind,
            actor_name=actor_name,
            api_key_id=api_key_id,
            client_ip=client_ip,
            has_request_body=has_request_body,
            has_response_body=has_response_body,
            rule_id=rule_id,
            trace_id=trace_id,
            user_agent=user_agent,
        )


        api_request_read.additional_properties = d
        return api_request_read

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
