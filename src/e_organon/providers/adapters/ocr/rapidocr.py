"""providers/adapters/ocr/rapidocr: words and their boxes off an image with RapidOCR (PP-OCR on onnxruntime), in process.

The engine won the bench against Tesseract (`docs/bench/ocr.md`): PP-OCRv5 mobile — a detector and one `latin` recogniser,
which reads Spanish and English alike, so the `language` hint goes unused. Its models are fetched, sha256-checked, into
`models` when the adapter opens (`Global.model_root_dir`), once: later starts find them. An engine is not thread-safe: every
read takes the adapter's lock, off the loop in a worker thread, and the sizes are read from the header alone."""

import io
import threading
import warnings
from typing import TYPE_CHECKING, ClassVar, Final, Self, cast

import anyio
from PIL import Image, UnidentifiedImageError
from rapidocr import LangDet, LangRec, ModelType, OCRVersion, RapidOCR

from e_organon.infra.errors import ParseError, ProviderError
from e_organon.infra.logger import logger
from e_organon.ports.ocr import OcrWord
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from pathlib import Path

    from rapidocr.utils.output import RapidOCROutput

### the bench's arm r5: the PP-OCRv5 mobile detector with the `latin` recogniser.
PARAMS: Final[dict[str, object]] = {
    "Global.log_level": "error",
    "Det.ocr_version": OCRVersion.PPOCRV5,
    "Det.lang_type": LangDet.CH,
    "Det.model_type": ModelType.MOBILE,
    "Rec.ocr_version": OCRVersion.PPOCRV5,
    "Rec.lang_type": LangRec.LATIN,
    "Rec.model_type": ModelType.MOBILE,
}


##### ADAPTER #####
class RapidocrAdapter:
    """Word-level OCR; the engine is built, its models fetched, when it opens."""

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        "rapidocr", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.SERIAL, warmup=True
    )

    __slots__ = ("_engine", "_lock", "_models")

    def __init__(self, *, models: Path) -> None:
        self._models = models
        self._lock = threading.Lock()
        self._engine: RapidOCR | None = None

    ##### PRIVATE #####

    def _enter_engine(self) -> RapidOCR:
        self._models.mkdir(parents=True, exist_ok=True)
        try:
            return RapidOCR(params={**PARAMS, "Global.model_root_dir": str(self._models)})
        except Exception as error:
            msg = f"the OCR models could not be loaded into {self._models}: {error}"
            raise ProviderError(msg) from error

    @staticmethod
    def _size_read(data: bytes) -> tuple[int, int]:
        try:
            ### only the service's budget refuses a large image: Pillow's own warning would be noise before its verdict.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    return image.size
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            msg = f"not a readable image: {error}"
            raise ParseError(msg) from error

    @staticmethod
    def _read_words(result: RapidOCROutput) -> tuple[OcrWord, ...]:
        """Every word of every line, in reading order, its box the extent of its four corners; a page without text has
        no `txts` and a placeholder in `word_results`, which is no word."""
        ### the library types `word_results` one level short: a tuple of lines, each a tuple of (text, score, corners).
        lines = cast(
            "tuple[tuple[tuple[str, float, list[list[int]]], ...], ...]", result.word_results if result.txts else ()
        )
        return tuple(
            OcrWord(
                text=text,
                box=(
                    float(min(x for x, _ in corners)),
                    float(min(y for _, y in corners)),
                    float(max(x for x, _ in corners)),
                    float(max(y for _, y in corners)),
                ),
            )
            for line in lines
            for text, _, corners in line
        )

    def _read_run(self, data: bytes) -> tuple[OcrWord, ...]:
        self._size_read(data)
        match self._engine:
            case None:
                msg = "RapidocrAdapter is not open: the lifespan opens it, callers never do"
                raise ProviderError(msg)
            case engine:
                with self._lock:
                    return self._read_words(cast("RapidOCROutput", engine(data, return_word_box=True)))

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        self._engine = await anyio.to_thread.run_sync(self._enter_engine)
        logger.info("rapidocr ready", models=str(self._models))
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._engine = None

    async def health(self) -> bool:
        return self._engine is not None

    async def size(self, data: bytes) -> tuple[int, int]:
        return await anyio.to_thread.run_sync(self._size_read, data)

    async def read(self, data: bytes, language: str) -> tuple[OcrWord, ...]:  # noqa: ARG002 — the port's hint; one `latin` model needs none
        return await anyio.to_thread.run_sync(self._read_run, data)
