from collections.abc import Callable, Awaitable
from datetime import datetime, timezone

from pinky_core.event.delivery import DeliveryTarget
from pinky_core.event.models import Event
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.outbox_repository import OutboxRepository


class OutboxPublisher:
    def __init__(
        self,
        *,
        outbox_repository: OutboxRepository,
        event_repository: SQLiteEventRepository,
        delivery_target: DeliveryTarget,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._outbox_repository = outbox_repository
        self._event_repository = event_repository
        self._delivery_target = delivery_target
        self._clock = clock or self._utc_now

    async def publish_pending(self, *, limit: int = 100) -> None:
        rows = await self._outbox_repository.get_pending(limit=limit)

        for row in rows:
            event = await self._event_repository.get(row.event_id)

            if event is None:
                await self._outbox_repository.record_failure(
                    outbox_id=row.outbox_id,
                    attempt_count=row.attempt_count + 1,
                    last_attempt_at=self._clock().isoformat(),
                    next_attempt_at=None,
                    last_error=f"Event not found: {row.event_id}",
                )
                continue

            try:
                await self._delivery_target(event)
            except Exception as exc:
                await self._outbox_repository.record_failure(
                    outbox_id=row.outbox_id,
                    attempt_count=row.attempt_count + 1,
                    last_attempt_at=self._clock().isoformat(),
                    next_attempt_at=None,
                    last_error=str(exc),
                )
                continue

            await self._outbox_repository.mark_published(
                outbox_id=row.outbox_id,
                published_at=self._clock().isoformat(),
            )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)