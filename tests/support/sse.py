"""tests/support/sse: the shape of the server-sent reader fixture."""

from collections.abc import Callable

type Told = Callable[[str], list[tuple[str, dict]]]
