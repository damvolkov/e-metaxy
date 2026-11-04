"""tests/support/bridge: the shapes of the bridge fixtures — a builder of engines over a scripted coder, and the wait that
settles a task."""

from collections.abc import Awaitable, Callable

from e_organon.engines.bridge import BridgeEngine, Task

type Wire = Callable[..., BridgeEngine]
type Settle = Callable[[BridgeEngine, Task], Awaitable[Task]]
