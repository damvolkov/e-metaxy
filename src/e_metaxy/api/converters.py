"""e_metaxy.api.converters: the converters as a REST surface — POST a file, get its Markdown back.

`/md` renders any file (the fast, any-format path); `/doc` reads a document deeply; `/health` answers. A file
arrives as a multipart upload (the standard file protocol); the response is the same typed payload the MCP
tools return, so an agent or a client can call either. A processor refusal — not a supported format, too big,
a zip bomb — is answered 400 with its reason, never a 500 an agent cannot read."""

from typing import TYPE_CHECKING, Any, cast

import msgspec
from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from e_metaxy.core.struct import CheckedStruct
from e_metaxy.processors.md import MDError

if TYPE_CHECKING:
    from e_metaxy.logic.converters import Converters


async def _refused(_request: Request, exc: Exception) -> JSONResponse:
    """A processor refusal is a 400 with its reason, never a 500 an agent cannot read."""
    return JSONResponse({"error": str(exc)}, status_code=400)


class ConverterApi:
    """The REST handlers over one wired `Converters`."""

    __slots__ = ("_converters",)

    def __init__(self, converters: Converters) -> None:
        self._converters = converters

    ##### PRIVATE #####

    @staticmethod
    async def _upload(request: Request) -> tuple[bytes, str]:
        """The multipart body as (bytes, name): the file's bytes (spool closed) and its uploaded filename."""
        file = cast("UploadFile", (await request.form())["file"])
        raw = await file.read()
        await file.close()
        return raw, getattr(file, "filename", "") or ""

    @staticmethod
    def _json(model: Any) -> JSONResponse:
        """A result model as a JSON response, flattened through the checked-struct encoder."""
        return JSONResponse(msgspec.to_builtins(model, enc_hook=CheckedStruct.enc_hook))

    ############################################################

    ##### PUBLIC #####

    async def md(self, request: Request) -> JSONResponse:
        """Render an uploaded file to Markdown — the fast, any-format path (a PDF here is quick context)."""
        raw, name = await self._upload(request)
        return self._json(await self._converters.markdown(raw, name=name))

    async def doc(self, request: Request) -> JSONResponse:
        """Read an uploaded document deeply: its outline and full text, tables and scans and all."""
        raw, name = await self._upload(request)
        return self._json(await self._converters.document(raw, name=name))

    async def health(self, _request: Request) -> JSONResponse:
        """Liveness: the REST surface is mounted and wired."""
        return JSONResponse({"status": "ok"})

    def routes(self) -> list[BaseRoute]:
        """The three endpoints, for mounting under `/ops`."""
        return [
            Route("/md", self.md, methods=["POST"]),
            Route("/doc", self.doc, methods=["POST"]),
            Route("/health", self.health, methods=["GET"]),
        ]


def create_app(converters: Converters) -> Starlette:
    """The REST sub-app; the composition root mounts it under `/ops`, so routes land on `/ops/md` and `/ops/doc`."""
    api = ConverterApi(converters)
    return Starlette(routes=api.routes(), exception_handlers={MDError: _refused})
