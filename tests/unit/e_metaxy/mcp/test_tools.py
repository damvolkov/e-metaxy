"""tests/unit/e_metaxy/mcp/tools: both surfaces over a live in-memory MCP client — the bridge's work, session
and live tools on a scripted coder, and the converter tools on a stub port and on the real anytomd engine
(`doc_read` falls back to the engine's own PDF reading when docling-serve is out of reach; a real image is
described by the vision model, skipped without a key)."""

import base64
import os
import pathlib
import struct
import zlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from fakes import stub
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from e_metaxy.adapters.anytomd import AnytomdAdapter
from e_metaxy.adapters.docling import DoclingAdapter
from e_metaxy.core.settings.base import Secret
from e_metaxy.core.settings.md import MDSettings
from e_metaxy.logic.converters import Converters
from e_metaxy.mcp.tools import TOOLS, ConverterTools
from e_metaxy.models.task import TaskState
from e_metaxy.processors.doc import DocProcessor
from e_metaxy.processors.md import MDProcessor

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fakes import Connect

PDF = pathlib.Path(__file__).resolve().parents[3] / "resources" / "documents" / "filing.pdf"
B64_PDF = base64.b64encode(PDF.read_bytes()).decode()
KEY = os.environ.get("MD_VISION_API_KEY")


def converter(fail: Exception | None = None, settings: MDSettings | None = None) -> ConverterTools:
    return ConverterTools(Converters(MDProcessor(stub(fail=fail), settings), DocProcessor(stub())))


def png(rgb: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * 40 for _ in range(40))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 40, 40, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


@asynccontextmanager
async def live_server() -> AsyncGenerator[Client]:
    settings = MDSettings(md_image_describe=True, md_vision_api_key=Secret(KEY) if KEY else None)
    anytomd, docling = AnytomdAdapter(settings), DoclingAdapter()
    surface = ConverterTools(Converters(MDProcessor(anytomd, settings), DocProcessor(docling)))
    async with anytomd, docling:
        server = MCPServer(name="md-doc")
        _ = [server.add_tool(surface.convert, name="md_convert"), server.add_tool(surface.read, name="doc_read")]
        async with Client(server) as client:
            yield client


async def test_tools_listed_with_hints(connect: Connect) -> None:
    async with connect() as client:
        listed = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert sorted(listed) == sorted(TOOLS)
        hints = {name: tool.annotations for name, tool in listed.items()}
        assert (hints["session_read"] and hints["session_read"].read_only_hint) is True
        assert (hints["work_cancel"] and hints["work_cancel"].destructive_hint) is True
        assert listed["work_start"].title == "Start work in Claude Code"


async def test_tools_work_start_lists_the_profiles(connect: Connect) -> None:
    async with connect() as client:
        start = next(tool for tool in (await client.list_tools()).tools if tool.name == "work_start")
        assert "- research (dontAsk): read and search only" in (start.description or "")
        assert "{profiles}" not in (start.description or "")


async def test_tools_work_flow(connect: Connect) -> None:
    async with connect() as client:
        started = await client.call_tool("work_start", {"prompt": "ping", "profile": "research", "project": "/tmp"})
        task = started.structured_content
        assert (started.is_error, task["state"]) == (False, TaskState.RUNNING)
        status = (await client.call_tool("work_status", {"task": task["id"], "wait": 2})).structured_content
        listed = await client.call_tool("work_list", {"limit": 5})
        assert (status["state"], status["result"], [t["id"] for t in listed.structured_content["result"]]) == (
            "done",
            "pong",
            [task["id"]],
        )


async def test_tools_work_cancel_finished(connect: Connect) -> None:
    async with connect() as client:
        task = (
            await client.call_tool("work_start", {"prompt": "p", "profile": "research", "project": "/tmp"})
        ).structured_content
        await client.call_tool("work_status", {"task": task["id"], "wait": 2})
        assert (await client.call_tool("work_cancel", {"task": task["id"]})).structured_content["state"] == "done"


async def test_tools_catalog(connect: Connect) -> None:
    async with connect() as client:
        catalog = (await client.call_tool("catalog", {"project": "/tmp"})).structured_content
        assert ([c["name"] for c in catalog["commands"]], [a["name"] for a in catalog["agents"]]) == (
            ["research"],
            ["architect"],
        )


async def test_tools_session_find_read_update(connect: Connect) -> None:
    async with connect() as client:
        found = (await client.call_tool("session_find", {"text": "voice"})).structured_content["result"]
        read = (await client.call_tool("session_read", {"session": "s-new", "last": 2})).structured_content
        updated = (
            await client.call_tool("session_update", {"session": "s-new", "title": "vad fixed", "tag": "done"})
        ).structured_content
        assert [row["session"] for row in found] == ["s-new"]
        assert [(t["role"], t["text"]) for t in read["turns"]] == [
            ("tool", "Edit"),
            ("assistant", "Threshold lowered to 0.4; tests green."),
        ]
        assert (updated["title"], updated["tag"]) == ("vad fixed", "done")


async def test_tools_live(connect: Connect) -> None:
    async with connect() as client:
        peers = (await client.call_tool("live_list", {})).structured_content["result"]
        receipt = (await client.call_tool("live_send", {"peer": peers[0]["name"], "text": "hola"})).structured_content
        assert ([p["status"] for p in peers], receipt["delivered"]) == (["busy"], True)


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("work_start", {"prompt": "p", "profile": "nope", "project": "/tmp"}, "unknown profile"),
        ("work_start", {"prompt": "p", "profile": "research", "project": "/etc"}, "outside the roots"),
        ("work_start", {"prompt": "p", "profile": "research", "project": "no-such-project"}, "no project named"),
        ("work_status", {"task": "missing"}, "unknown task"),
        ("session_read", {"session": "gone"}, "unknown session"),
        ("session_update", {"session": "gone", "title": "x"}, "unknown session"),
    ],
    ids=["profile", "root", "project", "task", "read", "update"],
)
async def test_tools_refused(connect: Connect, tool: str, arguments: dict, message: str) -> None:
    async with connect() as client:
        result = await client.call_tool(tool, arguments)
        assert result.is_error
        assert message in str(result.content)


async def test_tools_scope_missing_refused(connect: Connect, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("e_metaxy.mcp.tools.get_access_token", lambda: SimpleNamespace(scopes=["sessions"]))
    async with connect() as client:
        refused = await client.call_tool("work_list", {})
        allowed = await client.call_tool("session_find", {})
        assert (refused.is_error, "lacks the 'work' scope" in str(refused.content), allowed.is_error) == (
            True,
            True,
            False,
        )


async def test_tools_converter_content_is_decoded_and_rendered() -> None:
    entry = (await converter().convert(name="a.html", content=base64.b64encode(b"<h1>Hi</h1>").decode()))["files"][0]
    assert (entry["name"], entry["markdown"], entry["source"], entry["error"]) == ("a.md", "# A", "html", "")


async def test_tools_converter_a_server_path_is_read_and_named(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "note.html"
    source.write_bytes(b"<h1>Hi</h1>")
    assert (await converter().convert(path=str(source)))["files"][0]["name"] == "note.md"


async def test_tools_converter_a_file_must_arrive_by_path_or_content() -> None:
    with pytest.raises(ToolError, match=r"path.*content"):
        await converter().convert()


async def test_tools_converter_a_refusal_becomes_the_tool_error_message() -> None:
    with pytest.raises(ToolError, match="not a format"):
        await converter().convert(name="mystery", content=base64.b64encode(b"\xff\xfe\x00\x01blob").decode())


async def test_tools_converter_an_oversized_file_is_refused() -> None:
    with pytest.raises(ToolError, match="MD_MAX_INPUT_BYTES"):
        await converter(settings=MDSettings(md_max_input_bytes=4)).convert(name="a.html", content="PGgxPkhpPC9oMT4=")


async def test_tools_converter_an_engine_failure_is_reported_per_file_not_raised() -> None:
    files = (await converter(fail=RuntimeError("engine refused")).convert(name="x.html", content="eA=="))["files"]
    assert files[0]["error"] == "RuntimeError: engine refused"
    assert files[0]["markdown"] == ""


async def test_tools_converter_md_convert_renders_a_real_pdf() -> None:
    async with live_server() as client:
        files = (await client.call_tool("md_convert", {"name": "filing.pdf", "content": B64_PDF})).structured_content[
            "files"
        ]
    assert files[0]["source"] == "pdf"
    assert "10-K" in files[0]["markdown"]


async def test_tools_converter_doc_read_deep_reads_a_real_pdf() -> None:
    async with live_server() as client:
        summary = (await client.call_tool("doc_read", {"name": "filing.pdf", "content": B64_PDF})).structured_content
    assert summary["pages"] >= 1
    assert "10-K" in summary["markdown"]


@pytest.mark.skipif(not KEY, reason="no vision key (set MD_VISION_API_KEY)")
async def test_tools_converter_md_convert_describes_a_real_image() -> None:
    async with live_server() as client:
        files = (
            await client.call_tool(
                "md_convert", {"name": "square.png", "content": base64.b64encode(png((30, 140, 60))).decode()}
            )
        ).structured_content["files"]
    assert files[0]["source"] == "image"
    markdown = files[0]["markdown"]
    assert markdown.startswith("![")
    assert "](" in markdown
