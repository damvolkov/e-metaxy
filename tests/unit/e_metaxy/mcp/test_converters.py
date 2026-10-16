"""tests/unit/e_metaxy/mcp/converters: the processor tools — transport, the error boundary, and the real anytomd engine over a live in-memory MCP client.

The unit cases drive the tools over a stub port (detection and mapping are the real ones); the integration
cases wire the actual binding and a real PDF through the in-memory `Client` — `md_convert` renders it, the
deep `doc_read` runs `DocProcessor` and falls back to the engine's own PDF reading when docling-serve is out
of reach, and a real image is described by the vision model (skipped without a key)."""

import base64
import os
import pathlib
import struct
import zlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from e_metaxy.adapters.docling import DoclingAdapter
from e_metaxy.adapters.md.anytomd import AnytomdAdapter
from e_metaxy.adapters.ports import MdConversion
from e_metaxy.core.settings.base import Secret
from e_metaxy.core.settings.md import MDSettings
from e_metaxy.logic.converters import Converters
from e_metaxy.mcp.converters import ProcessorTools
from e_metaxy.processors.doc import DocProcessor
from e_metaxy.processors.md import MDProcessor

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

PDF = pathlib.Path(__file__).resolve().parents[3] / "resources" / "documents" / "filing.pdf"
B64_PDF = base64.b64encode(PDF.read_bytes()).decode()
KEY = os.environ.get("MD_VISION_API_KEY")


def stub(*, fail: Exception | None = None) -> Any:
    async def convert(data: bytes, *, extension: str) -> MdConversion:
        if fail:
            raise fail
        return MdConversion(markdown="# A")

    return SimpleNamespace(convert=convert, name="stub")


def processors(fail: Exception | None = None) -> ProcessorTools:
    return ProcessorTools(Converters(MDProcessor(stub(fail=fail)), DocProcessor(stub())))


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
    anatomd, docling = AnytomdAdapter(settings), DoclingAdapter()
    surface = ProcessorTools(Converters(MDProcessor(anatomd, settings), DocProcessor(docling)))
    async with anatomd, docling:
        server = MCPServer(name="md-doc")
        _ = [server.add_tool(surface.convert, name="md_convert"), server.add_tool(surface.read, name="doc_read")]
        async with Client(server) as client:
            yield client


async def test_content_is_decoded_and_rendered() -> None:
    entry = (await processors().convert(name="a.html", content=base64.b64encode(b"<h1>Hi</h1>").decode()))["files"][0]
    assert (entry["name"], entry["markdown"], entry["source"], entry["error"]) == ("a.md", "# A", "html", "")


async def test_a_server_path_is_read_and_named(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "note.html"
    source.write_bytes(b"<h1>Hi</h1>")
    assert (await processors().convert(path=str(source)))["files"][0]["name"] == "note.md"


async def test_a_file_must_arrive_by_path_or_content() -> None:
    with pytest.raises(ToolError, match=r"path.*content"):
        await processors().convert()


async def test_a_refusal_becomes_the_tool_error_message() -> None:
    with pytest.raises(ToolError, match="not a format"):
        await processors().convert(name="mystery", content=base64.b64encode(b"\xff\xfe\x00\x01blob").decode())


async def test_an_engine_failure_is_reported_per_file_not_raised() -> None:
    files = (await processors(fail=RuntimeError("engine refused")).convert(name="x.html", content="eA=="))["files"]
    assert files[0]["error"] == "RuntimeError: engine refused"
    assert files[0]["markdown"] == ""


async def test_md_convert_renders_a_real_pdf() -> None:
    async with live_server() as client:
        files = (await client.call_tool("md_convert", {"name": "filing.pdf", "content": B64_PDF})).structured_content[
            "files"
        ]
    assert files[0]["source"] == "pdf"
    assert "10-K" in files[0]["markdown"]


async def test_doc_read_deep_reads_a_real_pdf() -> None:
    async with live_server() as client:
        summary = (await client.call_tool("doc_read", {"name": "filing.pdf", "content": B64_PDF})).structured_content
    assert summary["pages"] >= 1
    assert "10-K" in summary["markdown"]


@pytest.mark.skipif(not KEY, reason="no vision key (set MD_VISION_API_KEY)")
async def test_md_convert_describes_a_real_image() -> None:
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
