from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.push_keys import PushKeys





T = TypeVar("T", bound="PushSubscriptionCreate")



@_attrs_define
class PushSubscriptionCreate:
    """ The browser's ``PushSubscription.toJSON()`` plus an optional label.

        Attributes:
            endpoint (str):
            keys (PushKeys):
            label (None | str | Unset):
     """

    endpoint: str
    keys: PushKeys
    label: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.push_keys import PushKeys # noqa: PLC0415
        endpoint = self.endpoint

        keys = self.keys.to_dict()

        label: None | str | Unset
        if isinstance(self.label, Unset):
            label = UNSET
        else:
            label = self.label


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "endpoint": endpoint,
            "keys": keys,
        })
        if label is not UNSET:
            field_dict["label"] = label

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.push_keys import PushKeys # noqa: PLC0415
        d = dict(src_dict)
        endpoint = d.pop("endpoint")

        keys = PushKeys.from_dict(d.pop("keys"))




        def _parse_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        label = _parse_label(d.pop("label", UNSET))


        push_subscription_create = cls(
            endpoint=endpoint,
            keys=keys,
            label=label,
        )


        push_subscription_create.additional_properties = d
        return push_subscription_create

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
