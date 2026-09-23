from collections.abc import Awaitable, Callable

from pinky_core.event.models import Event

DeliveryTarget = Callable[[Event], Awaitable[None]]