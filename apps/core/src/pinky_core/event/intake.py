from datetime import UTC, datetime

from .models import Event, IncomingEvent


class EventIntake:
    """
    Converts incoming source events into immutable Pinky Events.
    """

    def __init__(self, clock=None):
        self._clock = clock or self._utc_now

    async def accept(self, incoming: IncomingEvent) -> Event:
        received_at = self._clock()

        return Event.from_incoming(
            incoming,
            received_at=received_at,
        )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)
