from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.input_kind import InputKind
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.input_read_config import InputReadConfig
  from ..models.input_read_secret_fields_set import InputReadSecretFieldsSet





T = TypeVar("T", bound="InputRead")



@_attrs_define
class InputRead:
    """ 
        Attributes:
            created_at (None | str):
            id (int):
            kind (InputKind):
            name (str):
            updated_at (None | str):
            config (InputReadConfig | Unset):
            enabled (bool | Unset):  Default: True.
            secret_fields_set (InputReadSecretFieldsSet | Unset):
     """

    created_at: None | str
    id: int
    kind: InputKind
    name: str
    updated_at: None | str
    config: InputReadConfig | Unset = UNSET
    enabled: bool | Unset = True
    secret_fields_set: InputReadSecretFieldsSet | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.input_read_config import InputReadConfig # noqa: PLC0415
        from ..models.input_read_secret_fields_set import InputReadSecretFieldsSet # noqa: PLC0415
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
        if secret_fields_set is not UNSET:
            field_dict["secret_fields_set"] = secret_fields_set

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.input_read_config import InputReadConfig # noqa: PLC0415
        from ..models.input_read_secret_fields_set import InputReadSecretFieldsSet # noqa: PLC0415
        d = dict(src_dict)
        def _parse_created_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        created_at = _parse_created_at(d.pop("created_at"))


        id = d.pop("id")

        kind = InputKind(d.pop("kind"))




        name = d.pop("name")

        def _parse_updated_at(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        updated_at = _parse_updated_at(d.pop("updated_at"))


        _config = d.pop("config", UNSET)
        config: InputReadConfig | Unset
        if isinstance(_config,  Unset):
            config = UNSET
        else:
            config = InputReadConfig.from_dict(_config)




        enabled = d.pop("enabled", UNSET)

        _secret_fields_set = d.pop("secret_fields_set", UNSET)
        secret_fields_set: InputReadSecretFieldsSet | Unset
        if isinstance(_secret_fields_set,  Unset):
            secret_fields_set = UNSET
        else:
            secret_fields_set = InputReadSecretFieldsSet.from_dict(_secret_fields_set)




        input_read = cls(
            created_at=created_at,
            id=id,
            kind=kind,
            name=name,
            updated_at=updated_at,
            config=config,
            enabled=enabled,
            secret_fields_set=secret_fields_set,
        )


        input_read.additional_properties = d
        return input_read

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
