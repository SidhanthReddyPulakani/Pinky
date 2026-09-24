from abc import ABC, abstractmethod


class EventReader(ABC):
    """Source-specific observer that produces IncomingEvents."""

    @abstractmethod
    async def run(self) -> None:
        """Start observing the external source."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop observing the external source."""
        ...