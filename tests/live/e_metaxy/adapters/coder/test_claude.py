"""Live: the real Claude Code on this host, through the subscription login. Spends a little quota — `make live`."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from claude_agent_sdk import ClaudeAgentOptions, SystemMessage, query

from e_metaxy.adapters.coder.claude import ClaudeCoder
from e_metaxy.models.coder import CoderSpec, FinishedEvent, StartedEvent
from e_metaxy.models.profile import Profile

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.live

BOOK = Path(__file__).resolve().parents[4] / "resources" / "profiles" / "book.yaml"


@pytest.fixture
def research() -> Profile:
    return Profile.book(BOOK.read_bytes())["research"]


async def test_claude_live_run(research: Profile) -> None:
    init: list[dict] = []

    async def tapped(*, prompt: str, options: ClaudeAgentOptions) -> AsyncIterator[object]:
        async for message in query(prompt=prompt, options=options):
            match message:
                case SystemMessage(subtype="init", data=data):
                    init.append(data)
            yield message

    spec = CoderSpec(prompt="Reply with exactly the word pong and nothing else.", cwd="/tmp", profile=research)
    events = [event async for event in ClaudeCoder(runner=tapped).run(spec)]
    started, finished = events
    assert isinstance(started, StartedEvent)
    assert isinstance(finished, FinishedEvent)
    assert (finished.failed, "pong" in finished.result.lower(), finished.session) == (False, True, started.session)
    assert init[0]["apiKeySource"] == "none"


async def test_claude_live_resume(research: Profile) -> None:
    first = [
        e
        async for e in ClaudeCoder().run(
            CoderSpec(prompt="Remember the number 4817. Reply ok.", cwd="/tmp", profile=research)
        )
    ]
    session = first[0].session
    again = [
        e
        async for e in ClaudeCoder().run(
            CoderSpec(
                prompt="Which number did I ask you to remember? Digits only.",
                cwd="/tmp",
                profile=research,
                session=session,
            )
        )
    ]
    match again[-1]:
        case FinishedEvent(result=result):
            assert "4817" in result
        case other:
            pytest.fail(f"no finish: {other!r}")


async def test_claude_live_peers() -> None:
    async with ClaudeCoder() as claude:
        peers = await claude.peers()
    assert peers
    assert all(peer.name for peer in peers)
