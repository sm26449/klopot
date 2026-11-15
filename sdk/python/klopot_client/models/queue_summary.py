from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.queue_summary_states import QueueSummaryStates





T = TypeVar("T", bound="QueueSummary")



@_attrs_define
class QueueSummary:
    """ 
        Attributes:
            name (str):
            oldest_overdue_seconds (float):
            oldest_pending_seconds (float):
            overdue (int):
            states (QueueSummaryStates):
     """

    name: str
    oldest_overdue_seconds: float
    oldest_pending_seconds: float
    overdue: int
    states: QueueSummaryStates
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.queue_summary_states import QueueSummaryStates # noqa: PLC0415
        name = self.name

        oldest_overdue_seconds = self.oldest_overdue_seconds

        oldest_pending_seconds = self.oldest_pending_seconds

        overdue = self.overdue

        states = self.states.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "name": name,
            "oldest_overdue_seconds": oldest_overdue_seconds,
            "oldest_pending_seconds": oldest_pending_seconds,
            "overdue": overdue,
            "states": states,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.queue_summary_states import QueueSummaryStates # noqa: PLC0415
        d = dict(src_dict)
        name = d.pop("name")

        oldest_overdue_seconds = d.pop("oldest_overdue_seconds")

        oldest_pending_seconds = d.pop("oldest_pending_seconds")

        overdue = d.pop("overdue")

        states = QueueSummaryStates.from_dict(d.pop("states"))




        queue_summary = cls(
            name=name,
            oldest_overdue_seconds=oldest_overdue_seconds,
            oldest_pending_seconds=oldest_pending_seconds,
            overdue=overdue,
            states=states,
        )


        queue_summary.additional_properties = d
        return queue_summary

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
