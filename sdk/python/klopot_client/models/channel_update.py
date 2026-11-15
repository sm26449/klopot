from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.channel_kind import ChannelKind
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.channel_update_config_type_0 import ChannelUpdateConfigType0
  from ..models.channel_update_quiet_hours_type_0 import ChannelUpdateQuietHoursType0





T = TypeVar("T", bound="ChannelUpdate")



@_attrs_define
class ChannelUpdate:
    """ 
        Attributes:
            config (ChannelUpdateConfigType0 | None | Unset):
            enabled (bool | None | Unset):
            kind (ChannelKind | None | Unset):
            quiet_hours (ChannelUpdateQuietHoursType0 | None | Unset):
            rate_limit_per_min (int | None | Unset):
     """

    config: ChannelUpdateConfigType0 | None | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    kind: ChannelKind | None | Unset = UNSET
    quiet_hours: ChannelUpdateQuietHoursType0 | None | Unset = UNSET
    rate_limit_per_min: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.channel_update_config_type_0 import ChannelUpdateConfigType0 # noqa: PLC0415
        from ..models.channel_update_quiet_hours_type_0 import ChannelUpdateQuietHoursType0 # noqa: PLC0415
        config: dict[str, Any] | None | Unset
        if isinstance(self.config, Unset):
            config = UNSET
        elif isinstance(self.config, ChannelUpdateConfigType0):
            config = self.config.to_dict()
        else:
            config = self.config

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        kind: None | str | Unset
        if isinstance(self.kind, Unset):
            kind = UNSET
        elif isinstance(self.kind, ChannelKind):
            kind = self.kind.value
        else:
            kind = self.kind

        quiet_hours: dict[str, Any] | None | Unset
        if isinstance(self.quiet_hours, Unset):
            quiet_hours = UNSET
        elif isinstance(self.quiet_hours, ChannelUpdateQuietHoursType0):
            quiet_hours = self.quiet_hours.to_dict()
        else:
            quiet_hours = self.quiet_hours

        rate_limit_per_min: int | None | Unset
        if isinstance(self.rate_limit_per_min, Unset):
            rate_limit_per_min = UNSET
        else:
            rate_limit_per_min = self.rate_limit_per_min


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if config is not UNSET:
            field_dict["config"] = config
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if kind is not UNSET:
            field_dict["kind"] = kind
        if quiet_hours is not UNSET:
            field_dict["quiet_hours"] = quiet_hours
        if rate_limit_per_min is not UNSET:
            field_dict["rate_limit_per_min"] = rate_limit_per_min

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.channel_update_config_type_0 import ChannelUpdateConfigType0 # noqa: PLC0415
        from ..models.channel_update_quiet_hours_type_0 import ChannelUpdateQuietHoursType0 # noqa: PLC0415
        d = dict(src_dict)
        def _parse_config(data: object) -> ChannelUpdateConfigType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                config_type_0 = ChannelUpdateConfigType0.from_dict(data)



                return config_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChannelUpdateConfigType0 | None | Unset, data)

        config = _parse_config(d.pop("config", UNSET))


        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))


        def _parse_kind(data: object) -> ChannelKind | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                kind_type_0 = ChannelKind(data)



                return kind_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChannelKind | None | Unset, data)

        kind = _parse_kind(d.pop("kind", UNSET))


        def _parse_quiet_hours(data: object) -> ChannelUpdateQuietHoursType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                quiet_hours_type_0 = ChannelUpdateQuietHoursType0.from_dict(data)



                return quiet_hours_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChannelUpdateQuietHoursType0 | None | Unset, data)

        quiet_hours = _parse_quiet_hours(d.pop("quiet_hours", UNSET))


        def _parse_rate_limit_per_min(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        rate_limit_per_min = _parse_rate_limit_per_min(d.pop("rate_limit_per_min", UNSET))


        channel_update = cls(
            config=config,
            enabled=enabled,
            kind=kind,
            quiet_hours=quiet_hours,
            rate_limit_per_min=rate_limit_per_min,
        )


        channel_update.additional_properties = d
        return channel_update

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
