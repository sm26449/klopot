from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.setup_step import SetupStep





T = TypeVar("T", bound="SetupStatus")



@_attrs_define
class SetupStatus:
    """ 
        Attributes:
            complete (bool): Every step is done.
            dismissed (bool): An admin hid the guide (POST /v1/setup/dismiss); reopen brings it back.
            steps (list[SetupStep]):
            timezone (str): ALERTD_TZ — quiet hours, schedules and the digest use it.
     """

    complete: bool
    dismissed: bool
    steps: list[SetupStep]
    timezone: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.setup_step import SetupStep # noqa: PLC0415
        complete = self.complete

        dismissed = self.dismissed

        steps = []
        for steps_item_data in self.steps:
            steps_item = steps_item_data.to_dict()
            steps.append(steps_item)



        timezone = self.timezone


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "complete": complete,
            "dismissed": dismissed,
            "steps": steps,
            "timezone": timezone,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.setup_step import SetupStep # noqa: PLC0415
        d = dict(src_dict)
        complete = d.pop("complete")

        dismissed = d.pop("dismissed")

        steps = []
        _steps = d.pop("steps")
        for steps_item_data in (_steps):
            steps_item = SetupStep.from_dict(steps_item_data)



            steps.append(steps_item)


        timezone = d.pop("timezone")

        setup_status = cls(
            complete=complete,
            dismissed=dismissed,
            steps=steps,
            timezone=timezone,
        )


        setup_status.additional_properties = d
        return setup_status

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
