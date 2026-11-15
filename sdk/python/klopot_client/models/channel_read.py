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
  from ..models.channel_read_config import ChannelReadConfig
  from ..models.channel_read_quiet_hours_type_0 import ChannelReadQuietHoursType0
  from ..models.channel_read_secret_fields_set import ChannelReadSecretFieldsSet





T = TypeVar("T", bound="ChannelRead")



@_attrs_define
class ChannelRead:
    """ 
        Attributes:
            created_at (None | str):
            id (int):
            kind (ChannelKind):
            name (str):
            updated_at (None | str):
            config (ChannelReadConfig | Unset):
            enabled (bool | Unset):  Default: True.
            quiet_hours (ChannelReadQuietHoursType0 | None | Unset): This channel's own quiet window, applied by gating in
                the service timezone (audit A05). Contract: {"window": "22-07"} (HH or HH:MM, crosses midnight). Omit/null =
                never quiet. Separate from a template's per-channel quiet_hours map.
            rate_limit_per_min (int | Unset):  Default: 30.
            secret_fields_set (ChannelReadSecretFieldsSet | Unset):
     """

    created_at: None | str
    id: int
    kind: ChannelKind
    name: str
    updated_at: None | str
    config: ChannelReadConfig | Unset = UNSET
    enabled: bool | Unset = True
    quiet_hours: ChannelReadQuietHoursType0 | None | Unset = UNSET
    rate_limit_per_min: int | Unset = 30
    secret_fields_set: ChannelReadSecretFieldsSet | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.channel_read_config import ChannelReadConfig # noqa: PLC0415
        from ..models.channel_read_quiet_hours_type_0 import ChannelReadQuietHoursType0 # noqa: PLC0415
        from ..models.channel_read_secret_fields_set import ChannelReadSecretFieldsSet # noqa: PLC0415
        created_at: None | str
        created_at = self.created_at

        id = self.id

        kind = self.kind.value

        name = self.name

        updated_at: None | str
        updated_at = self.updated_at

        config: dict[str, Any] | Unset = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        enabled = self.enabled

        quiet_hours: dict[str, Any] | None | Unset
        if isinstance(self.quiet_hours, Unset):
            quiet_hours = UNSET
        elif isinstance(self.quiet_hours, ChannelReadQuietHoursType0):
            quiet_hours = self.quiet_hours.to_dict()
        else:
            quiet_hours = self.quiet_hours

        rate_limit_per_min = self.rate_limit_per_min

        secret_fields_set: dict[str, Any] | Unset = UNSET
        if not isinstance(self.secret_fields_set, Unset):
            secret_fields_set = self.secret_fields_set.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "created_at": created_at,
            "id": id,
            "kind": kind,
            "name": name,
            "updated_at": updated_at,
        })
        if config is not UNSET:
            field_dict["config"] = config
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if quiet_hours is not UNSET:
            field_dict["quiet_hours"] = quiet_hours
        if rate_limit_per_min is not UNSET:
            field_dict["rate_limit_per_min"] = rate_limit_per_min
        if secret_fields_set is not UNSET:
            field_dict["secret_fields_set"] = secret_fields_set

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.channel_read_config import ChannelReadConfig # noqa: PLC0415
        from ..models.channel_read_quiet_hours_type_0 import ChannelReadQuietHoursType0 # noqa: PLC0415
        from ..models.channel_read_secret_fields_set import ChannelReadSecretFieldsSet # noqa: PLC0415
        d = dict(src_dict)
        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        id = d.pop("id")

        kind = ChannelKind(d.pop("kind"))




        name = d.pop("name")

        def _parse_updated_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))


        _config = d.pop("config", UNSET)
        config: ChannelReadConfig | Unset
        if isinstance(_config,  Unset):
            config = UNSET
        else:
            config = ChannelReadConfig.from_dict(_config)




        enabled = d.pop("enabled", UNSET)

        def _parse_quiet_hours(data: object) -> ChannelReadQuietHoursType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                quiet_hours_type_0 = ChannelReadQuietHoursType0.from_dict(data)



                return quiet_hours_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ChannelReadQuietHoursType0 | None | Unset, data)

        quiet_hours = _parse_quiet_hours(d.pop("quiet_hours", UNSET))


        rate_limit_per_min = d.pop("rate_limit_per_min", UNSET)

        _secret_fields_set = d.pop("secret_fields_set", UNSET)
        secret_fields_set: ChannelReadSecretFieldsSet | Unset
        if isinstance(_secret_fields_set,  Unset):
            secret_fields_set = UNSET
        else:
            secret_fields_set = ChannelReadSecretFieldsSet.from_dict(_secret_fields_set)




        channel_read = cls(
            created_at=created_at,
            id=id,
            kind=kind,
            name=name,
            updated_at=updated_at,
            config=config,
            enabled=enabled,
            quiet_hours=quiet_hours,
            rate_limit_per_min=rate_limit_per_min,
            secret_fields_set=secret_fields_set,
        )


        channel_read.additional_properties = d
        return channel_read

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
