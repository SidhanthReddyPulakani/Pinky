from pinky_core.event.models import Event


class EventValidation:
    def validate(self, event: Event) -> Event:
        self._validate_event_type(event)
        self._validate_source(event)
        self._validate_timestamps(event)
        self._validate_schema_version(event)

        return event

    @staticmethod
    def _validate_event_type(event: Event) -> None:
        if not event.event_type.strip():
            raise ValueError("Event type must not be empty")

    @staticmethod
    def _validate_source(event: Event) -> None:
        if not event.source.strip():
            raise ValueError("Event source must not be empty")

    @staticmethod
    def _validate_timestamps(event: Event) -> None:
        if event.occurred_at > event.received_at:
            raise ValueError("Event occurred_at must not be later than received_at")

    @staticmethod
    def _validate_schema_version(event: Event) -> None:
        if event.schema_version < 1:
            raise ValueError("Event schema_version must be >= 1")
