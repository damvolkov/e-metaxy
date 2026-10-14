"""Test doubles shared across the unit tree: a scripted coder, a recording notifier, their event scripts."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, ClassVar

from claude_agent_sdk import SystemMessage
from mcp import Client

from e_metaxy.logic.bridge import Bridge
from e_metaxy.models.coder import (
    CoderEvent,
    CoderPeer,
    CoderReceipt,
    CoderSession,
    CoderSpec,
    FinishedEvent,
    PeerStatus,
    StartedEvent,
)
from e_metaxy.models.profile import CoderKind
from e_metaxy.models.task import Task

type Wire = Callable[..., Bridge]
type Settle = Callable[[Bridge, Task], Awaitable[Task]]
type Connect = Callable[[], AbstractAsyncContextManager[Client]]


class ScriptedCoder:
    """Plays a fixed event script per run; `hold` parks the run after its first event until cancelled."""

    kind: ClassVar[CoderKind] = CoderKind.CLAUDE

    def __init__(self, script: list[CoderEvent], *, hold: bool = False, fail: Exception | None = None) -> None:
        self.script = script
        self.hold = hold
        self.fail = fail
        self.specs: list[CoderSpec] = []
        self.parked = asyncio.Event()

    async def run(self, spec: CoderSpec) -> AsyncIterator[CoderEvent]:
        self.specs.append(spec)
        for event in self.script[:1]:
            yield event
        self.parked.set()
        await (asyncio.Event().wait() if self.hold else asyncio.sleep(0))
        match self.fail:
            case Exception() as failure:
                raise failure
        for event in self.script[1:]:
            yield event

    async def peers(self) -> list[CoderPeer]:
        return [CoderPeer(name="e-engineer-bc", ref="1c9776", kind="interactive", status=PeerStatus.BUSY)]

    async def send(self, peer: str, text: str) -> CoderReceipt:
        return CoderReceipt(peer=peer, delivered=True, detail=text)

    async def history(self, cwd: str, limit: int) -> list[CoderSession]:
        return [CoderSession(session="s-old", title="earlier work", cwd=cwd or "/tmp")][:limit]


class RecordingNotifier:
    name: ClassVar[str] = "openhuman"

    def __init__(self) -> None:
        self.told: list[Task] = []

    async def notify(self, task: Task) -> None:
        self.told.append(task)


DONE_SCRIPT = [
    StartedEvent(session="s-1"),
    FinishedEvent(session="s-1", result="pong", cost=0.01, turns=1),
]


@asynccontextmanager
async def lifespan(app: Callable[..., Coroutine[Any, Any, None]]) -> AsyncGenerator[None]:
    """Drive an ASGI app's lifespan protocol: startup before the block, shutdown after."""
    inbox: asyncio.Queue[dict] = asyncio.Queue()
    outbox: asyncio.Queue[dict] = asyncio.Queue()
    runner = asyncio.create_task(app({"type": "lifespan", "asgi": {"version": "3.0"}}, inbox.get, outbox.put))
    await inbox.put({"type": "lifespan.startup"})
    started = await outbox.get()
    assert started["type"] == "lifespan.startup.complete", started
    try:
        yield
    finally:
        await inbox.put({"type": "lifespan.shutdown"})
        await outbox.get()
        await runner


INIT = SystemMessage(subtype="init", data={"session_id": "s-1", "apiKeySource": "none", "model": "m"})


def sdk_stream(messages: list[object], raises: Exception | None = None) -> Callable[..., AsyncIterator[object]]:
    """A stand-in for the SDK's `query`: yields the frames, then raises what the CLI would."""

    async def run(**_: object) -> AsyncIterator[object]:
        for message in messages:
            yield message
        match raises:
            case Exception() as failure:
                raise failure

    return run
