"""tests/support/jobs: the shape of the job fixtures — a conversion queued under a key, read as its job's id."""

from collections.abc import Awaitable, Callable

type Queued = Callable[[dict[str, str]], Awaitable[str]]
