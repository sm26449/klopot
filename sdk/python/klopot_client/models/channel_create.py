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
  from ..models.channel_create_config import ChannelCreateConfig
  from ..models.channel_create_quiet_hours_type_0 import ChannelCreateQuietHoursType0





T = TypeVar("T", bound="ChannelCreate")



@_attrs_define
class ChannelCreate:
    """ 
        Attributes:
            kind (ChannelKind):
            name (str):
            config (ChannelCreateConfig | Unset):
            enabled (bool | Unset):  Default: True.
            quiet_hours (ChannelCreateQuietHoursType0 | None | Unset): This channel's own quiet window, applied by gating in
                the service timezone (audit A05). Contract: {"window": "22-07"} (HH or HH:MM, crosses midnight). Omit/null =
                never quiet. Separate from a template's per-channel quiet_hours map.
            rate_limit_per_min (int | Unset):  Default: 30.
     """

    kind: ChannelKind
    name: str
    config: ChannelCreateConfig | Unset = UNSET
    enabled: bool | Unset = True
    quiet_hours: ChannelCreateQuietHoursType0 | None | Unset = UNSET
    rate_limit_per_min: int | Unset = 30
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.channel_create_config import ChannelCreateConfig # noqa: PLC0415
        from ..models.channel_create_quiet_hours_type_0 import ChannelCreateQuietHoursType0 # noqa: PLC0415
        kind = self.kind.value

        name = self.name

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        enabled = self.enabled

        quiet_hours: dict[str, Any] | None | Unset
        if isinstance(self.quiet_hours, Unset):
            quiet_hours = UNSET
        elif isinstance(self.quiet_hours, ChannelCreateQuietHoursType0):
            quiet_hours = self.quiet_hours.to_dict()
        else:
            quiet_hours = self.quiet_hours

        rate_limit_per_min = self.rate_limit_per_min


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "kind": kind,
            "name": name,
        })
        if config is not UNSET:
            field_dict["config"] = config
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if quiet_hours is not UNSET:
            field_dict["quiet_hours"] = quiet_hours
        if rate_limit_per_min is not UNSET:
            field_dict["rate_limit_per_min"] = rate_limit_per_min

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.channel_create_config import ChannelCreateConfig # noqa: PLC0415
        from ..models.channel_create_quiet_hours_type_0 import ChannelCreateQuietHoursType0 # noqa: PLC0415
        d = dict(src_dict)
        kind = ChannelKind(d.pop("kind"))




        name = d.pop("name")

        _config = d.pop("config", UNSET)
        config: ChannelCreateConfig | Unset
        if isinstance(_config,  Unset):
            config = UNSET
        else:
            config = ChannelCreateConfig.from_dict(_config)




        enabled = d.pop("enabled", UNSET)

        def _parse_quiet_hours(data: object) -> ChannelCreateQuietHoursType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                quiet_hours_type_0 = ChannelCreateQuietHoursType0.from_dict(data)



                return quiet_hours_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChannelCreateQuietHoursType0 | None | Unset, data)

        quiet_hours = _parse_quiet_hours(d.pop("quiet_hours", UNSET))


        rate_limit_per_min = d.pop("rate_limit_per_min", UNSET)

        channel_create = cls(
            kind=kind,
            name=name,
            config=config,
            enabled=enabled,
            quiet_hours=quiet_hours,
            rate_limit_per_min=rate_limit_per_min,
        )


        channel_create.additional_properties = d
        return channel_create

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
