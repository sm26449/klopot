from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.error_body import ErrorBody





T = TypeVar("T", bound="ErrorEnvelope")



@_attrs_define
class ErrorEnvelope:
    """ 
        Attributes:
            error (ErrorBody): Per-API_DESIGN.md error model. Clients receive this on 4xx/5xx.
     """

    error: ErrorBody
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.error_body import ErrorBody # noqa: PLC0415
        error = self.error.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "error": error,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.error_body import ErrorBody # noqa: PLC0415
        d = dict(src_dict)
        error = ErrorBody.from_dict(d.pop("error"))




        error_envelope = cls(
            error=error,
        )


        error_envelope.additional_properties = d
        return error_envelope

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
