from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.fire_request_status import FireRequestStatus
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.fire_request_context import FireRequestContext





T = TypeVar("T", bound="FireRequest")



@_attrs_define
class FireRequest:
    """ Body for ``POST /v1/fire``.

        Attributes:
            type_ (str):
            context (FireRequestContext | Unset):
            idempotency_key (None | str | Unset):
            resolved_type (None | str | Unset):
            source (None | str | Unset):
            status (FireRequestStatus | Unset):  Default: FireRequestStatus.FIRING.
            test (bool | Unset):  Default: False.
     """

    type_: str
    context: FireRequestContext | Unset = UNSET
    idempotency_key: None | str | Unset = UNSET
    resolved_type: None | str | Unset = UNSET
    source: None | str | Unset = UNSET
    status: FireRequestStatus | Unset = FireRequestStatus.FIRING
    test: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.fire_request_context import FireRequestContext # noqa: PLC0415
        type_ = self.type_

        context: dict[str, Any] | Unset = UNSET
        if not isinstance(self.context, Unset):
            context = self.context.to_dict()

        idempotency_key: None | str | Unset
        if isinstance(self.idempotency_key, Unset):
            idempotency_key = UNSET
        else:
            idempotency_key = self.idempotency_key

        resolved_type: None | str | Unset
        if isinstance(self.resolved_type, Unset):
            resolved_type = UNSET
        else:
            resolved_type = self.resolved_type

        source: None | str | Unset
        if isinstance(self.source, Unset):
            source = UNSET
        else:
            source = self.source

        status: str | Unset = UNSET
        if not isinstance(self.status, Unset):
            status = self.status.value


        test = self.test


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "type": type_,
        })
        if context is not UNSET:
            field_dict["context"] = context
        if idempotency_key is not UNSET:
            field_dict["idempotency_key"] = idempotency_key
        if resolved_type is not UNSET:
            field_dict["resolved_type"] = resolved_type
        if source is not UNSET:
            field_dict["source"] = source
        if status is not UNSET:
            field_dict["status"] = status
        if test is not UNSET:
            field_dict["test"] = test

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.fire_request_context import FireRequestContext # noqa: PLC0415
        d = dict(src_dict)
        type_ = d.pop("type")

        _context = d.pop("context", UNSET)
        context: FireRequestContext | Unset
        if isinstance(_context,  Unset):
            context = UNSET
        else:
            context = FireRequestContext.from_dict(_context)




        def _parse_idempotency_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        idempotency_key = _parse_idempotency_key(d.pop("idempotency_key", UNSET))


        def _parse_resolved_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        resolved_type = _parse_resolved_type(d.pop("resolved_type", UNSET))


        def _parse_source(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source = _parse_source(d.pop("source", UNSET))


        _status = d.pop("status", UNSET)
        status: FireRequestStatus | Unset
        if isinstance(_status,  Unset):
            status = UNSET
        else:
            status = FireRequestStatus(_status)




        test = d.pop("test", UNSET)

        fire_request = cls(
            type_=type_,
            context=context,
            idempotency_key=idempotency_key,
            resolved_type=resolved_type,
            source=source,
            status=status,
            test=test,
        )


        fire_request.additional_properties = d
        return fire_request

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
