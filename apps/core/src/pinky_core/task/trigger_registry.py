from collections import defaultdict
from uuid import UUID

from pinky_core.event.models import Event

from .triggers import TaskTrigger


class TriggerRegistry:
    """
    Runtime index of active task triggers.

    Persistence remains the authoritative source. The registry is
    reconstructible runtime state.
    """

    def __init__(self) -> None:
        self._by_event_type: dict[str, list[TaskTrigger]] = defaultdict(list)

    def register(self, trigger: TaskTrigger) -> None:
        self.unregister(trigger.trigger_id)

        event_type = trigger.definition.event_type
        self._by_event_type[event_type].append(trigger)

    def unregister(self, trigger_id: UUID) -> None:
        for event_type, triggers in list(self._by_event_type.items()):
            remaining = [
                trigger
                for trigger in triggers
                if trigger.trigger_id != trigger_id
            ]

            if remaining:
                self._by_event_type[event_type] = remaining
            else:
                del self._by_event_type[event_type]

    def matching_triggers(self, event: Event) -> list[TaskTrigger]:
        triggers = self._by_event_type.get(event.event_type, [])

        return [
            trigger
            for trigger in triggers
            if trigger.matches(event)
        ]

    def matching_task_ids(self, event: Event) -> list[UUID]:
        """
        Return each matching Task exactly once.

        Multiple triggers belonging to the same Task may match the
        same Event, but that does not produce multiple activation
        candidates.
        """
        task_ids: list[UUID] = []
        seen: set[UUID] = set()

        for trigger in self.matching_triggers(event):
            if trigger.task_id not in seen:
                seen.add(trigger.task_id)
                task_ids.append(trigger.task_id)

        return task_ids

    def clear(self) -> None:
        self._by_event_type.clear()