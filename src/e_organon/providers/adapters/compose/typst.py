"""providers/adapters/compose/typst: a template and its data composed into a PDF/A-2b with typst (Rust, in process).

The template reaches its data as `json(bytes(sys.inputs.data))`; it may read files under the root it is given and nowhere
else. The output is made reproducible: a fixed creation time, and only the fonts typst embeds (a host's own would change
the bytes from machine to machine). The same input is the same PDF, byte for byte (`docs/bench/compose.md`)."""

import json
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


##### ADAPTER #####
class TypstAdapter:
    """Template composition; nothing to open, nothing to close."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("typst", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.THREAD)

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

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def compose(self, source: bytes, data: Mapping[str, Any], root: Path) -> bytes:
        return await anyio.to_thread.run_sync(self._compose_run, source, data, root)
