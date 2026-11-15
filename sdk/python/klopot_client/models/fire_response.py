from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="FireResponse")



@_attrs_define
class FireResponse:
    """ Returned by both ``POST /v1/fire`` and rule-test endpoints.

        Attributes:
            channels (list[str]):
            dispatched (bool):
            id (str):
            message (str):
            severity (str):
            title (str):
            episode (None | str | Unset):
            incident_id (None | str | Unset):
            status (str | Unset):  Default: 'sent'.
            suppressed_reason (None | str | Unset):
     """

    channels: list[str]
    dispatched: bool
    id: str
    message: str
    severity: str
    title: str
    episode: None | str | Unset = UNSET
    incident_id: None | str | Unset = UNSET
    status: str | Unset = 'sent'
    suppressed_reason: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        channels = self.channels



        dispatched = self.dispatched

        id = self.id

        message = self.message

        severity = self.severity

        title = self.title

        episode: None | str | Unset
        if isinstance(self.episode, Unset):
            episode = UNSET
        else:
            episode = self.episode

        incident_id: None | str | Unset
        if isinstance(self.incident_id, Unset):
            incident_id = UNSET
        else:
            incident_id = self.incident_id

        status = self.status

        suppressed_reason: None | str | Unset
        if isinstance(self.suppressed_reason, Unset):
            suppressed_reason = UNSET
        else:
            suppressed_reason = self.suppressed_reason


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "channels": channels,
            "dispatched": dispatched,
            "id": id,
            "message": message,
            "severity": severity,
            "title": title,
        })
        if episode is not UNSET:
            field_dict["episode"] = episode
        if incident_id is not UNSET:
            field_dict["incident_id"] = incident_id
        if status is not UNSET:
            field_dict["status"] = status
        if suppressed_reason is not UNSET:
            field_dict["suppressed_reason"] = suppressed_reason

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        channels = cast(list[str], d.pop("channels"))


        dispatched = d.pop("dispatched")

        id = d.pop("id")

        message = d.pop("message")

        severity = d.pop("severity")

        title = d.pop("title")

        def _parse_episode(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        episode = _parse_episode(d.pop("episode", UNSET))


        def _parse_incident_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        incident_id = _parse_incident_id(d.pop("incident_id", UNSET))


        status = d.pop("status", UNSET)

        def _parse_suppressed_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        suppressed_reason = _parse_suppressed_reason(d.pop("suppressed_reason", UNSET))


        fire_response = cls(
            channels=channels,
            dispatched=dispatched,
            id=id,
            message=message,
            severity=severity,
            title=title,
            episode=episode,
            incident_id=incident_id,
            status=status,
            suppressed_reason=suppressed_reason,
        )


        fire_response.additional_properties = d
        return fire_response

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
