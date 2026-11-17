from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.pack_apply_default_existing import PackApplyDefaultExisting
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.pack_apply_decisions import PackApplyDecisions
  from ..models.pack_apply_params import PackApplyParams





T = TypeVar("T", bound="PackApply")



@_attrs_define
class PackApply:
    """ 
        Attributes:
            decisions (PackApplyDecisions | Unset): Per item "<section>:<key>": overwrite, skip or copy (as
                /v1/config/import/apply), or import for a new item. A new route to a template that already exists is skipped
                unless its decision is import (its preview item has existing_template: true).
            default_existing (PackApplyDefaultExisting | Unset): Action for an existing item that differs. Default:
                PackApplyDefaultExisting.SKIP.
            pack_id (None | str | Unset): A catalog pack (GET /v1/packs).
            params (PackApplyParams | Unset): Parameter values by name; omitted ones take their default.
            yaml (None | str | Unset): Your own pack, as YAML text.
     """

    decisions: PackApplyDecisions | Unset = UNSET
    default_existing: PackApplyDefaultExisting | Unset = PackApplyDefaultExisting.SKIP
    pack_id: None | str | Unset = UNSET
    params: PackApplyParams | Unset = UNSET
    yaml: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.pack_apply_decisions import PackApplyDecisions # noqa: PLC0415
        from ..models.pack_apply_params import PackApplyParams # noqa: PLC0415
        decisions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.decisions, Unset):
            decisions = self.decisions.to_dict()

        default_existing: str | Unset = UNSET
        if not isinstance(self.default_existing, Unset):
            default_existing = self.default_existing.value


        pack_id: None | str | Unset
        if isinstance(self.pack_id, Unset):
            pack_id = UNSET
        else:
            pack_id = self.pack_id

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        yaml: None | str | Unset
        if isinstance(self.yaml, Unset):
            yaml = UNSET
        else:
            yaml = self.yaml


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
        })
        if decisions is not UNSET:
            field_dict["decisions"] = decisions
        if default_existing is not UNSET:
            field_dict["default_existing"] = default_existing
        if pack_id is not UNSET:
            field_dict["pack_id"] = pack_id
        if params is not UNSET:
            field_dict["params"] = params
        if yaml is not UNSET:
            field_dict["yaml"] = yaml

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pack_apply_decisions import PackApplyDecisions # noqa: PLC0415
        from ..models.pack_apply_params import PackApplyParams # noqa: PLC0415
        d = dict(src_dict)
        _decisions = d.pop("decisions", UNSET)
        decisions: PackApplyDecisions | Unset
        if isinstance(_decisions,  Unset):
            decisions = UNSET
        else:
            decisions = PackApplyDecisions.from_dict(_decisions)




        _default_existing = d.pop("default_existing", UNSET)
        default_existing: PackApplyDefaultExisting | Unset
        if isinstance(_default_existing,  Unset):
            default_existing = UNSET
        else:
            default_existing = PackApplyDefaultExisting(_default_existing)




        def _parse_pack_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pack_id = _parse_pack_id(d.pop("pack_id", UNSET))


        _params = d.pop("params", UNSET)
        params: PackApplyParams | Unset
        if isinstance(_params,  Unset):
            params = UNSET
        else:
            params = PackApplyParams.from_dict(_params)




        def _parse_yaml(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        yaml = _parse_yaml(d.pop("yaml", UNSET))


        pack_apply = cls(
            decisions=decisions,
            default_existing=default_existing,
            pack_id=pack_id,
            params=params,
            yaml=yaml,
        )


        pack_apply.additional_properties = d
        return pack_apply

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
