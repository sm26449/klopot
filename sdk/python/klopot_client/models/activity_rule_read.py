from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset






T = TypeVar("T", bound="ActivityRuleRead")



@_attrs_define
class ActivityRuleRead:
    """ 
        Attributes:
            hits (Any):
            id (Any):
            name (Any):
            action (Any | Unset):
            enabled (Any | Unset):
            keep_days (Any | Unset): Keep matching rows this long; empty = log_retention_days.
            last_hit_at (Any | Unset):
            last_ip (Any | Unset):
            match_actor (Any | Unset): Glob on the API key / user name.
            match_ip (Any | Unset): Glob on the client IP, e.g. 10.0.0.*.
            match_method (Any | Unset): GET, POST… — empty = any.
            match_path (Any | Unset): Glob on the request path, e.g. /v1/health* or /v1/inputs/*/webhook.
            match_status (Any | Unset): 2xx, 4xx… or an exact code; empty = any.
            position (Any | Unset):
            request_body (Any | Unset):
            response_body (Any | Unset):
     """

    hits: Any
    id: Any
    name: Any
    action: Any | Unset = UNSET
    enabled: Any | Unset = UNSET
    keep_days: Any | Unset = UNSET
    last_hit_at: Any | Unset = UNSET
    last_ip: Any | Unset = UNSET
    match_actor: Any | Unset = UNSET
    match_ip: Any | Unset = UNSET
    match_method: Any | Unset = UNSET
    match_path: Any | Unset = UNSET
    match_status: Any | Unset = UNSET
    position: Any | Unset = UNSET
    request_body: Any | Unset = UNSET
    response_body: Any | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        hits = self.hits

        id = self.id

        name = self.name

        action = self.action

        enabled = self.enabled

        keep_days = self.keep_days

        last_hit_at = self.last_hit_at

        last_ip = self.last_ip

        match_actor = self.match_actor

        match_ip = self.match_ip

        match_method = self.match_method

        match_path = self.match_path

        match_status = self.match_status

        position = self.position

        request_body = self.request_body

        response_body = self.response_body


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "hits": hits,
            "id": id,
            "name": name,
        })
        if action is not UNSET:
            field_dict["action"] = action
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if keep_days is not UNSET:
            field_dict["keep_days"] = keep_days
        if last_hit_at is not UNSET:
            field_dict["last_hit_at"] = last_hit_at
        if last_ip is not UNSET:
            field_dict["last_ip"] = last_ip
        if match_actor is not UNSET:
            field_dict["match_actor"] = match_actor
        if match_ip is not UNSET:
            field_dict["match_ip"] = match_ip
        if match_method is not UNSET:
            field_dict["match_method"] = match_method
        if match_path is not UNSET:
            field_dict["match_path"] = match_path
        if match_status is not UNSET:
            field_dict["match_status"] = match_status
        if position is not UNSET:
            field_dict["position"] = position
        if request_body is not UNSET:
            field_dict["request_body"] = request_body
        if response_body is not UNSET:
            field_dict["response_body"] = response_body

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        hits = d.pop("hits")

        id = d.pop("id")

        name = d.pop("name")

        action = d.pop("action", UNSET)

        enabled = d.pop("enabled", UNSET)

        keep_days = d.pop("keep_days", UNSET)

        last_hit_at = d.pop("last_hit_at", UNSET)

        last_ip = d.pop("last_ip", UNSET)

        match_actor = d.pop("match_actor", UNSET)

        match_ip = d.pop("match_ip", UNSET)

        match_method = d.pop("match_method", UNSET)

        match_path = d.pop("match_path", UNSET)

        match_status = d.pop("match_status", UNSET)

        position = d.pop("position", UNSET)

        request_body = d.pop("request_body", UNSET)

        response_body = d.pop("response_body", UNSET)

        activity_rule_read = cls(
            hits=hits,
            id=id,
            name=name,
            action=action,
            enabled=enabled,
            keep_days=keep_days,
            last_hit_at=last_hit_at,
            last_ip=last_ip,
            match_actor=match_actor,
            match_ip=match_ip,
            match_method=match_method,
            match_path=match_path,
            match_status=match_status,
            position=position,
            request_body=request_body,
            response_body=response_body,
        )


        activity_rule_read.additional_properties = d
        return activity_rule_read

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
