"""providers/adapters/compose/typst: a template and its data composed into a PDF/A-2b with typst (Rust).

A template is code a caller supplied, so typst runs as a sandbox, not as a client. Each compile is its own process — a thread
cannot be killed, a process can — held to `timeout` from outside and to a memory ceiling, and the template reaches its data as
`json(bytes(sys.inputs.data))`. It may read files under the root it is given and nowhere else (typst's own project root). It
never fetches a package: the binding cannot switch downloads off, so a template naming one (`"@preview/…"`) is refused before
compiling, and the process's proxy points at nothing, so a name built at run time fails to connect too. The output is made
reproducible: a fixed creation time, only the fonts typst embeds. The same input is the same PDF, byte for byte
(`docs/bench/compose.md`)."""

import base64
import json
import re
import resource
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self, cast

import anyio
import typst

from e_organon.infra.errors import ParseError
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

### the PDF's creation time, whatever the clock says: reproducibility is the point.
CREATED: Final[datetime] = datetime(2000, 1, 1, tzinfo=UTC)
### a package is `@namespace/name:version` in a string: the text scan that refuses it before compiling.
PACKAGE: Final[re.Pattern[bytes]] = re.compile(rb"""["']@[\w-]+/""")
### what a compile may allocate, and where the process thinks the network is: nowhere.
MEMORY: Final[int] = 2 * 1024**3
DEAD: Final[str] = "http://127.0.0.1:9"
RUN: Final[tuple[str, ...]] = (
    sys.executable,
    "-I",
    "-c",
    "from e_organon.providers.adapters.compose.typst import TypstAdapter; TypstAdapter.work()",
)


##### ADAPTER #####
class TypstAdapter:
    """Template composition, one sandboxed process a compile; nothing to open, nothing to close."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("typst", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.PROCESS)

    __slots__ = ("_timeout",)

    def __init__(self, *, timeout: float) -> None:
        self._timeout = timeout

    ##### PRIVATE #####

    @staticmethod
    def _compose_run(source: bytes, data: Mapping[str, Any], root: Path) -> bytes:
        try:
            return typst.compile(
                source,
                ### typst's stub gives `root` the input's own type variable (bytes here): a path is what it takes.
                root=cast("Any", root),
                sys_inputs={"data": json.dumps(data, ensure_ascii=False, sort_keys=True)},
                pdf_standards="a-2b",
                timestamp=CREATED,
                ignore_system_fonts=True,
            )
        except typst.TypstError as error:
            msg = f"the template does not compose: {error.message}\n{error.diagnostic}".strip()
            raise ParseError(msg) from error

    @staticmethod
    def _compose_order(source: bytes, data: Mapping[str, Any], root: Path) -> tuple[bytes, Path]:
        """The order the sandbox reads and the folder it runs in: the root made absolute, since the process starts there."""
        folder = root.absolute()
        order = json.dumps({"source": base64.b64encode(source).decode(), "data": data, "root": str(folder)})
        return order.encode(), folder

    async def _compose_spawn(self, order: bytes, path: Path) -> bytes:
        try:
            with anyio.fail_after(self._timeout):
                done = await anyio.run_process(
                    list(RUN),
                    input=order,
                    check=False,
                    cwd=path,
                    env={
                        "PATH": "/usr/bin:/bin",
                        "HOME": "/nonexistent",
                        "HTTPS_PROXY": DEAD,
                        "HTTP_PROXY": DEAD,
                        "ALL_PROXY": DEAD,
                    },
                )
        except TimeoutError as error:
            msg = f"the template took longer than {self._timeout:g} s to compose and was stopped"
            raise ParseError(msg) from error
        match done.returncode:
            case 0:
                return done.stdout
            case _:
                msg = done.stderr.decode(errors="replace").strip() or f"the compiler died ({done.returncode})"
                raise ParseError(msg)

    ############################################################

    ##### PUBLIC #####

    @classmethod
    def work(cls) -> None:
        """The sandboxed process: one order on stdin (source, data, root), the PDF on stdout, the reason on stderr."""
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
        order = json.loads(sys.stdin.buffer.read())
        try:
            pdf = cls._compose_run(base64.b64decode(order["source"]), order["data"], order["root"])
        except ParseError as error:
            sys.stderr.write(str(error))
            sys.exit(1)
        sys.stdout.buffer.write(pdf)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def compose(self, source: bytes, data: Mapping[str, Any], root: Path) -> bytes:
        match PACKAGE.search(source):
            case None:
                order, folder = self._compose_order(source, data, root)
                return await self._compose_spawn(order, folder)
            case _:
                msg = "the template names a package: packages are not available, a template is self-contained"
                raise ParseError(msg)
