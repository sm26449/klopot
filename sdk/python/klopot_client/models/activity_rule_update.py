from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.activity_rule_update_action_type_0 import ActivityRuleUpdateActionType0
from ..models.activity_rule_update_request_body_type_0 import ActivityRuleUpdateRequestBodyType0
from ..models.activity_rule_update_response_body_type_0 import ActivityRuleUpdateResponseBodyType0
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="ActivityRuleUpdate")



@_attrs_define
class ActivityRuleUpdate:
    """ 
        Attributes:
            action (ActivityRuleUpdateActionType0 | None | Unset):
            enabled (bool | None | Unset):
            keep_days (int | None | Unset):
            match_actor (None | str | Unset):
            match_ip (None | str | Unset):
            match_method (None | str | Unset):
            match_path (None | str | Unset):
            match_status (None | str | Unset):
            name (None | str | Unset):
            position (int | None | Unset):
            request_body (ActivityRuleUpdateRequestBodyType0 | None | Unset):
            response_body (ActivityRuleUpdateResponseBodyType0 | None | Unset):
     """

    action: ActivityRuleUpdateActionType0 | None | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    keep_days: int | None | Unset = UNSET
    match_actor: None | str | Unset = UNSET
    match_ip: None | str | Unset = UNSET
    match_method: None | str | Unset = UNSET
    match_path: None | str | Unset = UNSET
    match_status: None | str | Unset = UNSET
    name: None | str | Unset = UNSET
    position: int | None | Unset = UNSET
    request_body: ActivityRuleUpdateRequestBodyType0 | None | Unset = UNSET
    response_body: ActivityRuleUpdateResponseBodyType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        action: None | str | Unset
        if isinstance(self.action, Unset):
            action = UNSET
        elif isinstance(self.action, ActivityRuleUpdateActionType0):
            action = self.action.value
        else:
            action = self.action

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
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

        match_path: None | str | Unset
        if isinstance(self.match_path, Unset):
            match_path = UNSET
        else:
            match_path = self.match_path

        match_status: None | str | Unset
        if isinstance(self.match_status, Unset):
            match_status = UNSET
        else:
            match_status = self.match_status

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        position: int | None | Unset
        if isinstance(self.position, Unset):
            position = UNSET
        else:
            position = self.position

        request_body: None | str | Unset
        if isinstance(self.request_body, Unset):
            request_body = UNSET
        elif isinstance(self.request_body, ActivityRuleUpdateRequestBodyType0):
            request_body = self.request_body.value
        else:
            request_body = self.request_body

        response_body: None | str | Unset
        if isinstance(self.response_body, Unset):
            response_body = UNSET
        elif isinstance(self.response_body, ActivityRuleUpdateResponseBodyType0):
            response_body = self.response_body.value
        else:
            response_body = self.response_body


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
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
        if name is not UNSET:
            field_dict["name"] = name
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
        def _parse_action(data: object) -> ActivityRuleUpdateActionType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                action_type_0 = ActivityRuleUpdateActionType0(data)



                return action_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ActivityRuleUpdateActionType0 | None | Unset, data)

        action = _parse_action(d.pop("action", UNSET))


        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))


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


        def _parse_match_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        match_path = _parse_match_path(d.pop("match_path", UNSET))


        def _parse_match_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        match_status = _parse_match_status(d.pop("match_status", UNSET))


        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))


        def _parse_position(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        position = _parse_position(d.pop("position", UNSET))


        def _parse_request_body(data: object) -> ActivityRuleUpdateRequestBodyType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                request_body_type_0 = ActivityRuleUpdateRequestBodyType0(data)



                return request_body_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ActivityRuleUpdateRequestBodyType0 | None | Unset, data)

        request_body = _parse_request_body(d.pop("request_body", UNSET))


        def _parse_response_body(data: object) -> ActivityRuleUpdateResponseBodyType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                response_body_type_0 = ActivityRuleUpdateResponseBodyType0(data)



                return response_body_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ActivityRuleUpdateResponseBodyType0 | None | Unset, data)

        response_body = _parse_response_body(d.pop("response_body", UNSET))


        activity_rule_update = cls(
            action=action,
            enabled=enabled,
            keep_days=keep_days,
            match_actor=match_actor,
            match_ip=match_ip,
            match_method=match_method,
            match_path=match_path,
            match_status=match_status,
            name=name,
            position=position,
            request_body=request_body,
            response_body=response_body,
        )


        activity_rule_update.additional_properties = d
        return activity_rule_update

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
