"""api.router.converters: the converters as a REST door — POST a file, get its Markdown back.

`/ops/md` renders any file (the fast, any-format path); `/ops/doc` reads a document deeply; `/ops/health`
proves the door and its bearer. A file arrives as a multipart upload; the answer is the same typed payload the
MCP tools return, so an agent or a client can call either. A processor refusal — not a supported format, too
big, a zip bomb — is a 400 with its reason, never a 500 an agent cannot read."""

from dataclasses import dataclass
from typing import Annotated, Any, Final

import msgspec
from litestar import Request, Response, get, post
from litestar.datastructures import UploadFile
from litestar.di import NamedDependency, Provide
from litestar.enums import RequestEncodingType
from litestar.handlers import HTTPRouteHandler
from litestar.params import Body
from litestar.status_codes import HTTP_200_OK, HTTP_400_BAD_REQUEST

from e_metaxy.api.deps import DepKey, converters, graph
from e_metaxy.api.security import SECURITY, auth_guard
from e_metaxy.core.struct import CheckedStruct
from e_metaxy.logic.converters import Converters
from e_metaxy.processors.md import MDError

PREFIX: Final = "/ops"


##### CONTRACT #####
@dataclass(frozen=True, slots=True)
class Upload:
    """The multipart form: one `file` field, its filename naming the format."""

    file: UploadFile


##### HELPERS #####
async def unpack(upload: Upload) -> tuple[bytes, str]:
    """The upload as (bytes, name), its spool closed."""
    raw = await upload.file.read()
    await upload.file.close()
    return raw, upload.file.filename or ""


def plain(model: object) -> Any:
    """A result model as JSON builtins, through the checked-struct encoder — what the MCP tools answer too."""
    return msgspec.to_builtins(model, enc_hook=CheckedStruct.enc_hook)


def refused(_request: Request[Any, Any, Any], exc: MDError) -> Response[dict[str, str]]:
    """A processor refusal is a 400 with its reason."""
    return Response({"error": str(exc)}, status_code=HTTP_400_BAD_REQUEST)


##### HANDLERS #####
async def md(
    data: Annotated[Upload, Body(media_type=RequestEncodingType.MULTI_PART)],
    converters: NamedDependency[Converters],
) -> dict[str, Any]:
    """Render an uploaded file to Markdown — the fast, any-format path (a PDF here is quick context)."""
    raw, name = await unpack(data)
    return plain(await converters.markdown(raw, name=name))


async def doc(
    data: Annotated[Upload, Body(media_type=RequestEncodingType.MULTI_PART)],
    converters: NamedDependency[Converters],
) -> dict[str, Any]:
    """Read an uploaded document deeply: its outline and full text, tables and scans and all."""
    raw, name = await unpack(data)
    return plain(await converters.document(raw, name=name))


async def health() -> dict[str, str]:
    """The REST door is mounted, wired and behind its bearer."""
    return {"status": "ok"}


##### CHAINS #####
CONVERTER_DEPS: Final[dict[str, Provide]] = {
    DepKey.GRAPH.value: Provide(graph, sync_to_thread=False),
    DepKey.CONVERTERS.value: Provide(converters, sync_to_thread=False),
}

##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = (
    post(
        "/md",
        name="ops.md",
        status_code=HTTP_200_OK,
        tags=["ops"],
        guards=[auth_guard],
        security=SECURITY,
        dependencies=CONVERTER_DEPS,
        exception_handlers={MDError: refused},
    )(md),
    post(
        "/doc",
        name="ops.doc",
        status_code=HTTP_200_OK,
        tags=["ops"],
        guards=[auth_guard],
        security=SECURITY,
        dependencies=CONVERTER_DEPS,
        exception_handlers={MDError: refused},
    )(doc),
    get("/health", name="ops.health", tags=["ops"], guards=[auth_guard], security=SECURITY)(health),
)
