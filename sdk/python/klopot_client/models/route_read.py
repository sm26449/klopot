from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.channel_kind import ChannelKind
from ..models.severity import Severity
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.route_read_channel_overrides_type_0 import RouteReadChannelOverridesType0





T = TypeVar("T", bound="RouteRead")



@_attrs_define
class RouteRead:
    """ One existing route (template ⇄ channel).

        Attributes:
            channel_id (int):
            channel_name (str):
            enabled (bool):
            kind (ChannelKind):
            severity_min (Severity):
            channel_overrides (None | RouteReadChannelOverridesType0 | Unset):
     """

    channel_id: int
    channel_name: str
    enabled: bool
    kind: ChannelKind
    severity_min: Severity
    channel_overrides: None | RouteReadChannelOverridesType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.route_read_channel_overrides_type_0 import RouteReadChannelOverridesType0 # noqa: PLC0415
        channel_id = self.channel_id

        channel_name = self.channel_name

        enabled = self.enabled

        kind = self.kind.value

        severity_min = self.severity_min.value

        channel_overrides: dict[str, Any] | None | Unset
        if isinstance(self.channel_overrides, Unset):
            channel_overrides = UNSET
        elif isinstance(self.channel_overrides, RouteReadChannelOverridesType0):
            channel_overrides = self.channel_overrides.to_dict()
        else:
            channel_overrides = self.channel_overrides


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "channel_id": channel_id,
            "channel_name": channel_name,
            "enabled": enabled,
            "kind": kind,
            "severity_min": severity_min,
        })
        if channel_overrides is not UNSET:
            field_dict["channel_overrides"] = channel_overrides

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.route_read_channel_overrides_type_0 import RouteReadChannelOverridesType0 # noqa: PLC0415
        d = dict(src_dict)
        channel_id = d.pop("channel_id")

        channel_name = d.pop("channel_name")

        enabled = d.pop("enabled")

        kind = ChannelKind(d.pop("kind"))




        severity_min = Severity(d.pop("severity_min"))




        def _parse_channel_overrides(data: object) -> None | RouteReadChannelOverridesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                channel_overrides_type_0 = RouteReadChannelOverridesType0.from_dict(data)



                return channel_overrides_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RouteReadChannelOverridesType0 | Unset, data)

        channel_overrides = _parse_channel_overrides(d.pop("channel_overrides", UNSET))


        route_read = cls(
            channel_id=channel_id,
            channel_name=channel_name,
            enabled=enabled,
            kind=kind,
            severity_min=severity_min,
            channel_overrides=channel_overrides,
        )


        route_read.additional_properties = d
        return route_read

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
