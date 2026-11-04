"""engines/artifact: a tool's output kept as a file — content-addressed under one folder, so it can be the next tool's
input. The same bytes land on the same path (`<stem>-<sha256[:12]><suffix>`): keeping twice writes once."""

import hashlib
from typing import TYPE_CHECKING

import anyio

if TYPE_CHECKING:
    from pathlib import Path


##### ENGINE #####
class ArtifactEngine:
    """Writes outputs under `root` (created on first use); answers where each one is."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()

    ##### PUBLIC #####

    async def keep(self, data: bytes, stem: str, suffix: str) -> Path:
        """The file holding `data`, named after `stem` and its content."""
        path = self._root / f"{stem}-{hashlib.sha256(data).hexdigest()[:12]}{suffix}"
        target = anyio.Path(path)
        await anyio.Path(self._root).mkdir(parents=True, exist_ok=True)
        _ = await target.exists() or await target.write_bytes(data)
        return path
