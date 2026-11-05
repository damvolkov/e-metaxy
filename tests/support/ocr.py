"""tests/support/ocr: an OCR engine of the tests' own — it reads any image as the words it was given, boxes in pixels."""

from typing import TYPE_CHECKING, ClassVar, Self

from e_organon.infra.errors import ParseError
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.ports.ocr import OcrWord


class FakeOcr:
    """The same words for every image; `size` is the PNG header's, `read` refuses what is no PNG."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("fake-ocr", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.SERIAL)

    def __init__(self, words: tuple[OcrWord, ...] = ()) -> None:
        self.words = words
        self.seen: list[tuple[int, int, str]] = []
        self.models: Path | None = None

    def keeping(self, models: Path) -> Self:
        """The adapter as the lifespan builds it: told where the models are kept."""
        self.models = models
        return self

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def size(self, data: bytes) -> tuple[int, int]:
        match data[:8] == b"\x89PNG\r\n\x1a\n":
            case False:
                msg = "not a readable image"
                raise ParseError(msg)
        return int.from_bytes(data[16:20]), int.from_bytes(data[20:24])

    async def read(self, data: bytes, language: str) -> tuple[OcrWord, ...]:
        width, height = await self.size(data)
        self.seen.append((width, height, language))
        return self.words
