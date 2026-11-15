from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.severity import Severity
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.route_write_channel_overrides_type_0 import RouteWriteChannelOverridesType0





T = TypeVar("T", bound="RouteWrite")



@_attrs_define
class RouteWrite:
    """ One desired route in a ``PUT .../channels`` set.

        Attributes:
            channel_id (int | None | Unset):
            channel_name (None | str | Unset):
            channel_overrides (None | RouteWriteChannelOverridesType0 | Unset):
            enabled (bool | Unset):  Default: True.
            severity_min (Severity | Unset):
     """

    channel_id: int | None | Unset = UNSET
    channel_name: None | str | Unset = UNSET
    channel_overrides: None | RouteWriteChannelOverridesType0 | Unset = UNSET
    enabled: bool | Unset = True
    severity_min: Severity | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.route_write_channel_overrides_type_0 import RouteWriteChannelOverridesType0 # noqa: PLC0415
        channel_id: int | None | Unset
        if isinstance(self.channel_id, Unset):
            channel_id = UNSET
        else:
            channel_id = self.channel_id

        channel_name: None | str | Unset
        if isinstance(self.channel_name, Unset):
            channel_name = UNSET
        else:
            channel_name = self.channel_name

        channel_overrides: dict[str, Any] | None | Unset
        if isinstance(self.channel_overrides, Unset):
            channel_overrides = UNSET
        elif isinstance(self.channel_overrides, RouteWriteChannelOverridesType0):
            channel_overrides = self.channel_overrides.to_dict()
        else:
            channel_overrides = self.channel_overrides

        enabled = self.enabled

        severity_min: str | Unset = UNSET
        if not isinstance(self.severity_min, Unset):
            severity_min = self.severity_min.value



        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if channel_id is not UNSET:
            field_dict["channel_id"] = channel_id
        if channel_name is not UNSET:
            field_dict["channel_name"] = channel_name
        if channel_overrides is not UNSET:
            field_dict["channel_overrides"] = channel_overrides
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if severity_min is not UNSET:
            field_dict["severity_min"] = severity_min

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.route_write_channel_overrides_type_0 import RouteWriteChannelOverridesType0 # noqa: PLC0415
        d = dict(src_dict)
        def _parse_channel_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        channel_id = _parse_channel_id(d.pop("channel_id", UNSET))


        def _parse_channel_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        channel_name = _parse_channel_name(d.pop("channel_name", UNSET))


        def _parse_channel_overrides(data: object) -> None | RouteWriteChannelOverridesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                channel_overrides_type_0 = RouteWriteChannelOverridesType0.from_dict(data)



                return channel_overrides_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RouteWriteChannelOverridesType0 | Unset, data)

        channel_overrides = _parse_channel_overrides(d.pop("channel_overrides", UNSET))


        enabled = d.pop("enabled", UNSET)

        _severity_min = d.pop("severity_min", UNSET)
        severity_min: Severity | Unset
        if isinstance(_severity_min,  Unset):
            severity_min = UNSET
        else:
            severity_min = Severity(_severity_min)




        route_write = cls(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_overrides=channel_overrides,
            enabled=enabled,
            severity_min=severity_min,
        )


        route_write.additional_properties = d
        return route_write

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
