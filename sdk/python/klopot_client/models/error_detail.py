from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.error_detail_detail_type_1_item import ErrorDetailDetailType1Item
  from ..models.error_detail_detail_type_2 import ErrorDetailDetailType2





T = TypeVar("T", bound="ErrorDetail")



@_attrs_define
class ErrorDetail:
    """ The body of an API error. ``detail`` is a message (most errors, and a
    domain 422), a list of validation errors (a 422 from request validation),
    or an object such as ``{"code": "TYPE_NOT_ALLOWED", "message": "…"}``.

        Attributes:
            detail (ErrorDetailDetailType2 | list[ErrorDetailDetailType1Item] | str):
     """

    detail: ErrorDetailDetailType2 | list[ErrorDetailDetailType1Item] | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.error_detail_detail_type_1_item import ErrorDetailDetailType1Item # noqa: PLC0415
        from ..models.error_detail_detail_type_2 import ErrorDetailDetailType2 # noqa: PLC0415
        detail: dict[str, Any] | list[dict[str, Any]] | str
        if isinstance(self.detail, list):
            detail = []
            for detail_type_1_item_data in self.detail:
                detail_type_1_item = detail_type_1_item_data.to_dict()
                detail.append(detail_type_1_item)


        elif isinstance(self.detail, ErrorDetailDetailType2):
            detail = self.detail.to_dict()
        else:
            detail = self.detail


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "detail": detail,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.error_detail_detail_type_1_item import ErrorDetailDetailType1Item # noqa: PLC0415
        from ..models.error_detail_detail_type_2 import ErrorDetailDetailType2 # noqa: PLC0415
        d = dict(src_dict)
        def _parse_detail(data: object) -> ErrorDetailDetailType2 | list[ErrorDetailDetailType1Item] | str:
            try:
                if not isinstance(data, list):
                    raise TypeError()
                detail_type_1 = []
                _detail_type_1 = data
                for detail_type_1_item_data in (_detail_type_1):
                    detail_type_1_item = ErrorDetailDetailType1Item.from_dict(detail_type_1_item_data)



                    detail_type_1.append(detail_type_1_item)

                return detail_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                detail_type_2 = ErrorDetailDetailType2.from_dict(data)



                return detail_type_2
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ErrorDetailDetailType2 | list[ErrorDetailDetailType1Item] | str, data)

        detail = _parse_detail(d.pop("detail"))


        error_detail = cls(
            detail=detail,
        )


        error_detail.additional_properties = d
        return error_detail

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
