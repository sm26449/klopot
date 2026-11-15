from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.import_apply_default_existing import ImportApplyDefaultExisting
from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.import_apply_decisions import ImportApplyDecisions





T = TypeVar("T", bound="ImportApply")



@_attrs_define
class ImportApply:
    """ 
        Attributes:
            yaml (str): The pack, as YAML text.
            decisions (ImportApplyDecisions | Unset): Per item, keyed "<section>:<key>" (e.g. "rules:soc_low"): overwrite,
                skip or copy. New items are imported unless skipped; identical ones are left alone.
            default_existing (ImportApplyDefaultExisting | Unset): Action for an existing item that differs and has no
                decision. Default: ImportApplyDefaultExisting.SKIP.
     """

    yaml: str
    decisions: ImportApplyDecisions | Unset = UNSET
    default_existing: ImportApplyDefaultExisting | Unset = ImportApplyDefaultExisting.SKIP
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.import_apply_decisions import ImportApplyDecisions # noqa: PLC0415
        yaml = self.yaml

        decisions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.decisions, Unset):
            decisions = self.decisions.to_dict()

        default_existing: str | Unset = UNSET
        if not isinstance(self.default_existing, Unset):
            default_existing = self.default_existing.value



        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "yaml": yaml,
        })
        if decisions is not UNSET:
            field_dict["decisions"] = decisions
        if default_existing is not UNSET:
            field_dict["default_existing"] = default_existing

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.import_apply_decisions import ImportApplyDecisions # noqa: PLC0415
        d = dict(src_dict)
        yaml = d.pop("yaml")

        _decisions = d.pop("decisions", UNSET)
        decisions: ImportApplyDecisions | Unset
        if isinstance(_decisions,  Unset):
            decisions = UNSET
        else:
            decisions = ImportApplyDecisions.from_dict(_decisions)




        _default_existing = d.pop("default_existing", UNSET)
        default_existing: ImportApplyDefaultExisting | Unset
        if isinstance(_default_existing,  Unset):
            default_existing = UNSET
        else:
            default_existing = ImportApplyDefaultExisting(_default_existing)




        import_apply = cls(
            yaml=yaml,
            decisions=decisions,
            default_existing=default_existing,
        )


        import_apply.additional_properties = d
        return import_apply

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
