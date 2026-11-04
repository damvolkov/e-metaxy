"""tests/support/coder: a `CoderPort` that plays a fixed script — the coder every tekton test runs on, in place of a Claude Code
that spends quota — and the stand-in for the Agent SDK's `query`.

`ScriptedCoder` plays its script per run: the first event, then (when `hold`) parks until cancelled, then the rest; `fail`
raises after the first event. Its recorded sessions, peers and catalog are fixed, so a test names them."""

import asyncio
from typing import TYPE_CHECKING, ClassVar, Final, Self

import msgspec
from claude_agent_sdk import SystemMessage

from e_organon.ports.coder import (
    CatalogEntry,
    CoderCatalog,
    CoderEvent,
    CoderKind,
    CoderPeer,
    CoderReceipt,
    CoderSession,
    CoderSpec,
    FinishedEvent,
    PeerStatus,
    SessionTurn,
    StartedEvent,
    TurnRole,
)
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

UUID: Final[str] = "7b4fb561-4dde-463f-b54b-e8c9114b3682"
DONE_SCRIPT: Final[tuple[CoderEvent, ...]] = (
    StartedEvent(session="s-1"),
    FinishedEvent(session="s-1", result="pong", cost=0.01, turns=1),
)
INIT: Final[SystemMessage] = SystemMessage(
    subtype="init", data={"session_id": "s-1", "apiKeySource": "none", "model": "m"}
)


class ScriptedCoder:
    """Plays a fixed event script per run; `hold` parks the run after its first event until cancelled."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("scripted", Locality.EMBEDDED, Workload.IO_BOUND, Isolation.LOOP)
    kind: ClassVar[CoderKind] = CoderKind.CLAUDE

    def __init__(
        self, script: tuple[CoderEvent, ...] = DONE_SCRIPT, *, hold: bool = False, fail: Exception | None = None
    ) -> None:
        self.script = script
        self.hold = hold
        self.fail = fail
        self.specs: list[CoderSpec] = []
        self.parked = asyncio.Event()
        self.known: dict[str, CoderSession] = {
            "s-new": CoderSession(session="s-new", title="fix the voice tests"),
            UUID: CoderSession(session=UUID, title="Tools MCP en tools.py"),
        }

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Nothing to release."""

    async def health(self) -> bool:
        return True

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

    async def sessions(self, cwd: str, limit: int) -> list[CoderSession]:
        rows = [
            CoderSession(
                session="s-new", title="fix the voice tests", cwd=cwd or "/tmp", branch="fix/vad", tag="voice"
            ),
            CoderSession(session="s-old", title="earlier work", cwd=cwd or "/tmp"),
            CoderSession(session=UUID, title="Tools MCP en tools.py", cwd=cwd or "/tmp"),
            CoderSession(session="7b4fb5ff-twin", title="a twin by prefix", cwd=cwd or "/tmp"),
        ]
        return rows[:limit]

    async def session(self, session: str) -> CoderSession | None:
        return self.known.get(session)

    async def turns(self, session: str, last: int) -> list[SessionTurn]:
        turns = [
            SessionTurn(role=TurnRole.USER, text="fix the vad threshold"),
            SessionTurn(role=TurnRole.TOOL, text="Edit"),
            SessionTurn(role=TurnRole.ASSISTANT, text="Threshold lowered to 0.4; tests green."),
        ]
        return turns[-last:] if session in self.known and last > 0 else []

    async def update(self, session: str, title: str | None, tag: str | None) -> None:
        current = self.known[session]
        self.known[session] = msgspec.structs.replace(
            current, title=title or current.title, tag=current.tag if tag is None else tag
        )

    async def catalog(self, cwd: str) -> CoderCatalog:
        return CoderCatalog(
            cwd=cwd,
            commands=(CatalogEntry(name="research", description="survey the state of the art", hint="<topic>"),),
            agents=(CatalogEntry(name="architect", description="boundaries before code"),),
        )


def sdk_stream(messages: list[object], raises: Exception | None = None) -> Callable[..., AsyncIterator[object]]:
    """A stand-in for the SDK's `query`: yields the frames, then raises what the CLI would."""

    async def run(**_: object) -> AsyncIterator[object]:
        for message in messages:
            yield message
        match raises:
            case Exception() as failure:
                raise failure

    return run
