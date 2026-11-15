from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.delivery_read_purpose import DeliveryReadPurpose
from ..models.delivery_read_state import DeliveryReadState
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="DeliveryRead")



@_attrs_define
class DeliveryRead:
    """ Operational delivery fields only; frozen credentials never leave the DB.

        Attributes:
            attempts (int):
            channel (str):
            created_at (None | str):
            id (int):
            last_error (None | str):
            lease_until (None | str):
            max_attempts (int):
            next_attempt_at (None | str):
            purpose (DeliveryReadPurpose):
            state (DeliveryReadState):
            updated_at (None | str):
            provider_ref (None | str | Unset):
     """

    attempts: int
    channel: str
    created_at: None | str
    id: int
    last_error: None | str
    lease_until: None | str
    max_attempts: int
    next_attempt_at: None | str
    purpose: DeliveryReadPurpose
    state: DeliveryReadState
    updated_at: None | str
    provider_ref: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        attempts = self.attempts

        channel = self.channel

        created_at: None | str
        created_at = self.created_at

        id = self.id

        last_error: None | str
        last_error = self.last_error

        lease_until: None | str
        lease_until = self.lease_until

        max_attempts = self.max_attempts

        next_attempt_at: None | str
        next_attempt_at = self.next_attempt_at

        purpose = self.purpose.value

        state = self.state.value

        updated_at: None | str
        updated_at = self.updated_at

        provider_ref: None | str | Unset
        if isinstance(self.provider_ref, Unset):
            provider_ref = UNSET
        else:
            provider_ref = self.provider_ref


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "attempts": attempts,
            "channel": channel,
            "created_at": created_at,
            "id": id,
            "last_error": last_error,
            "lease_until": lease_until,
            "max_attempts": max_attempts,
            "next_attempt_at": next_attempt_at,
            "purpose": purpose,
            "state": state,
            "updated_at": updated_at,
        })
        if provider_ref is not UNSET:
            field_dict["provider_ref"] = provider_ref

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        attempts = d.pop("attempts")

        channel = d.pop("channel")

        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        id = d.pop("id")

        def _parse_last_error(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        last_error = _parse_last_error(d.pop("last_error"))


        def _parse_lease_until(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        lease_until = _parse_lease_until(d.pop("lease_until"))


        max_attempts = d.pop("max_attempts")

        def _parse_next_attempt_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        next_attempt_at = _parse_next_attempt_at(d.pop("next_attempt_at"))


        purpose = DeliveryReadPurpose(d.pop("purpose"))




        state = DeliveryReadState(d.pop("state"))




        def _parse_updated_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))


        def _parse_provider_ref(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_ref = _parse_provider_ref(d.pop("provider_ref", UNSET))


        delivery_read = cls(
            attempts=attempts,
            channel=channel,
            created_at=created_at,
            id=id,
            last_error=last_error,
            lease_until=lease_until,
            max_attempts=max_attempts,
            next_attempt_at=next_attempt_at,
            purpose=purpose,
            state=state,
            updated_at=updated_at,
            provider_ref=provider_ref,
        )


        delivery_read.additional_properties = d
        return delivery_read

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
