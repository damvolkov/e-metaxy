"""tests/unit/e_organon/services/tekton/sessions: the tools that reach recorded and live sessions — catalog, find, read,
update, peers, send — each answering the coder's own values, a refusal naming the session."""

from typing import TYPE_CHECKING

from e_organon.models.tekton import CatalogIn, FindIn, PeersIn, ReadIn, SendIn, UpdateIn

if TYPE_CHECKING:
    from e_organon.services.tekton.catalog import CatalogTektonService
    from e_organon.services.tekton.find import FindTektonService
    from e_organon.services.tekton.peers import PeersTektonService
    from e_organon.services.tekton.read import ReadTektonService
    from e_organon.services.tekton.send import SendTektonService
    from e_organon.services.tekton.update import UpdateTektonService
    from support.flow import Answered, Refused


async def test_catalog_offers_commands_and_agents(catalog: CatalogTektonService, answered: Answered) -> None:
    steps, offered = await answered(catalog, CatalogIn(project="/tmp"))
    assert (steps, offered.cwd, [c.name for c in offered.commands], [a.name for a in offered.agents]) == (
        ["read"],
        "/tmp",
        ["research"],
        ["architect"],
    )


async def test_find_by_text_and_project(find: FindTektonService, answered: Answered) -> None:
    steps, voice = await answered(find, FindIn(text="VOICE"))
    _, in_tmp = await answered(find, FindIn(project="/tmp", limit=1))
    assert (steps, [s.session for s in voice.sessions], [s.cwd for s in in_tmp.sessions]) == (
        ["search"],
        ["s-new"],
        ["/tmp"],
    )


async def test_read_a_session_and_its_last_turns(read: ReadTektonService, answered: Answered) -> None:
    steps, found = await answered(read, ReadIn(session="s-new", last=1))
    assert (steps, found.session.title, [t.text for t in found.turns]) == (
        ["read"],
        "fix the voice tests",
        ["Threshold lowered to 0.4; tests green."],
    )


async def test_read_unknown_session_is_refused(read: ReadTektonService, refused: Refused) -> None:
    assert await refused(read, ReadIn(session="gone")) == (["read"], "UnknownSessionError")


async def test_update_renames_and_tags(update: UpdateTektonService, answered: Answered) -> None:
    steps, session = await answered(update, UpdateIn(session="s-new", title="vad fixed", tag="done"))
    assert (steps, session.title, session.tag) == (["update"], "vad fixed", "done")


async def test_update_unknown_session_is_refused(update: UpdateTektonService, refused: Refused) -> None:
    assert await refused(update, UpdateIn(session="gone", title="x")) == (["update"], "UnknownSessionError")


async def test_peers_are_the_open_sessions(peers: PeersTektonService, answered: Answered) -> None:
    steps, open_ = await answered(peers, PeersIn())
    assert (steps, [(p.name, p.status) for p in open_.peers]) == (["list"], [("e-engineer-bc", "busy")])


async def test_send_reaches_a_peer(send: SendTektonService, answered: Answered) -> None:
    steps, receipt = await answered(send, SendIn(peer="e-engineer-bc", text="hola"))
    assert (steps, receipt.peer, receipt.delivered) == (["send"], "e-engineer-bc", True)
