from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.test_rule_body_context import TestRuleBodyContext





T = TypeVar("T", bound="TestRuleBody")



@_attrs_define
class TestRuleBody:
    """ ``POST /v1/rules/{id}/test`` body — supply mock context.

        Attributes:
            context (TestRuleBodyContext | Unset):
            instance (None | str | Unset):
     """

    context: TestRuleBodyContext | Unset = UNSET
    instance: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.test_rule_body_context import TestRuleBodyContext # noqa: PLC0415
        context: dict[str, Any] | Unset = UNSET
        if not isinstance(self.context, Unset):
            context = self.context.to_dict()

        instance: None | str | Unset
        if isinstance(self.instance, Unset):
            instance = UNSET
        else:
            instance = self.instance


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if context is not UNSET:
            field_dict["context"] = context
        if instance is not UNSET:
            field_dict["instance"] = instance

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.test_rule_body_context import TestRuleBodyContext # noqa: PLC0415
        d = dict(src_dict)
        _context = d.pop("context", UNSET)
        context: TestRuleBodyContext | Unset
        if isinstance(_context,  Unset):
            context = UNSET
        else:
            context = TestRuleBodyContext.from_dict(_context)




        def _parse_instance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        instance = _parse_instance(d.pop("instance", UNSET))


        test_rule_body = cls(
            context=context,
            instance=instance,
        )


        test_rule_body.additional_properties = d
        return test_rule_body

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
