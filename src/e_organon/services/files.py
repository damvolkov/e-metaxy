"""e_organon.services.files: a path argument made safe — resolved, and refused outside the allowed roots."""

from pathlib import Path
from typing import Never

import anyio

from e_organon.models.error import OutsideRootsError


##### FILES #####
class AllowedFiles:
    """Resolves a caller's path against the allowed roots: symlinks and `..` resolved first, so none escapes them."""

    __slots__ = ("_roots",)

    def __init__(self, roots: tuple[Path, ...]) -> None:
        self._roots = tuple(root.expanduser().resolve() for root in roots)

    ##### PRIVATE #####

    def _resolve_refuse(self, path: str) -> Never:
        msg = f"{path!r} is not a file under {', '.join(map(str, self._roots))}"
        raise OutsideRootsError(msg)

    ############################################################

    ##### PUBLIC #####

    async def resolve(self, path: str) -> Path:
        """The real file `path` names, when it exists under an allowed root."""
        real = Path(await (await anyio.Path(path).expanduser()).resolve())
        allowed = any(real.is_relative_to(root) for root in self._roots) and await anyio.Path(real).is_file()
        return real if allowed else self._resolve_refuse(path)
