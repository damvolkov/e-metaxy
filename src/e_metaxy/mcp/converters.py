"""e_metaxy.mcp.converters: the processors as MCP tools — a file in, its Markdown out, for any agent.

`md_convert` renders any file to Markdown fast (a PDF here means quick context, not a deep read); `doc_read`
runs the deep reader over a document and hands back its outline and text. Both take a server-side `path` or
base64 `content` (with the `name` that names its format), and any refusal surfaces as the tool's message —
what an agent can act on — never an internal crash."""

import base64
from pathlib import PurePath
from typing import Any

import anyio
import msgspec
from beartype import beartype
from mcp.server.mcpserver.exceptions import ToolError

from e_metaxy.core.struct import CheckedStruct
from e_metaxy.logic.converters import Converters


@beartype
class ProcessorTools:
    """The MCP surface over the converters: render any file, or read a document deeply."""

    __slots__ = ("_converters",)

    def __init__(self, converters: Converters) -> None:
        self._converters = converters

    ##### PRIVATE #####

    @staticmethod
    async def _source(path: str, content: str, name: str) -> tuple[bytes, str]:
        """The file as bytes and a name: a server-side path wins, else base64 content; the name says the format."""
        match (path, content):
            case (server_path, _) if server_path:
                return await anyio.Path(server_path).read_bytes(), name or PurePath(server_path).name
            case (_, payload) if payload:
                return base64.b64decode(payload), name
            case _:
                msg = "send the file as a `path` on this host or as base64 `content`"
                raise ValueError(msg)

    async def _common_plain(self, run: Any) -> Any:
        """Run the tool's work as JSON builtins; any refusal or failure becomes the tool's message, never a crash."""
        try:
            value = await run()
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            raise ToolError(reason) from exc
        return msgspec.to_builtins(value, enc_hook=CheckedStruct.enc_hook)

    ############################################################

    ##### PUBLIC #####

    async def convert(self, *, name: str = "", path: str = "", content: str = "") -> dict[str, Any]:
        """Render any file — PDF, Word, Excel, PowerPoint, HTML, CSV, JSON, XML, code, text, an image, or a ZIP of
        them — to Markdown for context. Pass a `path` on this host or base64 `content`; `name` names the format when
        sending content. Returns `files`: one entry per file (a ZIP yields many), each with its Markdown, source
        format and engine, or an `error` for that one file."""

        async def run() -> Any:
            raw, label = await self._source(path, content, name)
            return await self._converters.markdown(raw, name=label)

        return await self._common_plain(run)

    async def read(self, *, name: str = "", path: str = "", content: str = "") -> dict[str, Any]:
        """Read a document deeply — a PDF whose tables, scans and figures matter. Where the fast `md_convert` only
        pulls context, this routes the hard pages to a deep engine. Pass a `path` or base64 `content`; `name` names
        the format. Returns the document's `markdown`, its `pages` and which were read deeply, and its `sections`
        (each heading with the text under it)."""

        async def run() -> Any:
            raw, label = await self._source(path, content, name)
            return await self._converters.document(raw, name=label)

        return await self._common_plain(run)
