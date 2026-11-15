from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.activity_rule_create_action import ActivityRuleCreateAction
from ..models.activity_rule_create_request_body import ActivityRuleCreateRequestBody
from ..models.activity_rule_create_response_body import ActivityRuleCreateResponseBody
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ActivityRuleCreate")



@_attrs_define
class ActivityRuleCreate:
    """ 
        Attributes:
            name (str):
            action (ActivityRuleCreateAction | Unset):  Default: ActivityRuleCreateAction.KEEP.
            enabled (bool | Unset):  Default: True.
            keep_days (int | None | Unset): Keep matching rows this long; empty = log_retention_days.
            match_actor (None | str | Unset): Glob on the API key / user name.
            match_ip (None | str | Unset): Glob on the client IP, e.g. 10.0.0.*.
            match_method (None | str | Unset): GET, POST… — empty = any.
            match_path (str | Unset): Glob on the request path, e.g. /v1/health* or /v1/inputs/*/webhook. Default: '*'.
            match_status (None | str | Unset): 2xx, 4xx… or an exact code; empty = any.
            position (int | Unset):  Default: 100.
            request_body (ActivityRuleCreateRequestBody | Unset):  Default: ActivityRuleCreateRequestBody.AUTO.
            response_body (ActivityRuleCreateResponseBody | Unset):  Default: ActivityRuleCreateResponseBody.AUTO.
     """

    name: str
    action: ActivityRuleCreateAction | Unset = ActivityRuleCreateAction.KEEP
    enabled: bool | Unset = True
    keep_days: int | None | Unset = UNSET
    match_actor: None | str | Unset = UNSET
    match_ip: None | str | Unset = UNSET
    match_method: None | str | Unset = UNSET
    match_path: str | Unset = '*'
    match_status: None | str | Unset = UNSET
    position: int | Unset = 100
    request_body: ActivityRuleCreateRequestBody | Unset = ActivityRuleCreateRequestBody.AUTO
    response_body: ActivityRuleCreateResponseBody | Unset = ActivityRuleCreateResponseBody.AUTO
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        name = self.name

        action: str | Unset = UNSET
        if not isinstance(self.action, Unset):
            action = self.action.value


        enabled = self.enabled

        keep_days: int | None | Unset
        if isinstance(self.keep_days, Unset):
            keep_days = UNSET
        else:
            keep_days = self.keep_days

        match_actor: None | str | Unset
        if isinstance(self.match_actor, Unset):
            match_actor = UNSET
        else:
            match_actor = self.match_actor

        match_ip: None | str | Unset
        if isinstance(self.match_ip, Unset):
            match_ip = UNSET
        else:
            match_ip = self.match_ip

        match_method: None | str | Unset
        if isinstance(self.match_method, Unset):
            match_method = UNSET
        else:
            match_method = self.match_method

        match_path = self.match_path

        match_status: None | str | Unset
        if isinstance(self.match_status, Unset):
            match_status = UNSET
        else:
            match_status = self.match_status

        position = self.position

        request_body: str | Unset = UNSET
        if not isinstance(self.request_body, Unset):
            request_body = self.request_body.value


        response_body: str | Unset = UNSET
        if not isinstance(self.response_body, Unset):
            response_body = self.response_body.value



        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
        })
        if action is not UNSET:
            field_dict["action"] = action
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if keep_days is not UNSET:
            field_dict["keep_days"] = keep_days
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
        name = d.pop("name")

        _action = d.pop("action", UNSET)
        action: ActivityRuleCreateAction | Unset
        if isinstance(_action,  Unset):
            action = UNSET
        else:
            action = ActivityRuleCreateAction(_action)




        enabled = d.pop("enabled", UNSET)

        def _parse_keep_days(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        keep_days = _parse_keep_days(d.pop("keep_days", UNSET))


        def _parse_match_actor(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        match_actor = _parse_match_actor(d.pop("match_actor", UNSET))


        def _parse_match_ip(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        match_ip = _parse_match_ip(d.pop("match_ip", UNSET))


        def _parse_match_method(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        match_method = _parse_match_method(d.pop("match_method", UNSET))


        match_path = d.pop("match_path", UNSET)

        def _parse_match_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        match_status = _parse_match_status(d.pop("match_status", UNSET))


        position = d.pop("position", UNSET)

        _request_body = d.pop("request_body", UNSET)
        request_body: ActivityRuleCreateRequestBody | Unset
        if isinstance(_request_body,  Unset):
            request_body = UNSET
        else:
            request_body = ActivityRuleCreateRequestBody(_request_body)




        _response_body = d.pop("response_body", UNSET)
        response_body: ActivityRuleCreateResponseBody | Unset
        if isinstance(_response_body,  Unset):
            response_body = UNSET
        else:
            response_body = ActivityRuleCreateResponseBody(_response_body)




        activity_rule_create = cls(
            name=name,
            action=action,
            enabled=enabled,
            keep_days=keep_days,
            match_actor=match_actor,
            match_ip=match_ip,
            match_method=match_method,
            match_path=match_path,
            match_status=match_status,
            position=position,
            request_body=request_body,
            response_body=response_body,
        )


        activity_rule_create.additional_properties = d
        return activity_rule_create

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
