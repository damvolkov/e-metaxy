"""tests/support/jobs: the shape of the job fixtures — a conversion queued under a key (settled, when asked), read as its
job's id."""

from typing import Protocol


class Queued(Protocol):
    async def __call__(self, key: dict[str, str], *, settled: bool = False) -> str: ...
