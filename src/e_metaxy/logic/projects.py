"""e_metaxy.logic.projects: a project by the name a person says — `e-voice` — or by its path.

A short name is looked up one and two levels under the workspace root (`~/workspaces/<name>`,
`~/workspaces/<owner>/<name>`); anything with a slash or a `~` is already a path. An unknown or ambiguous
name is a typed refusal that lists what it could have meant, so an agent can ask or retry."""

from pathlib import Path

from beartype import beartype

from e_metaxy.models.error import AmbiguousProjectError, UnknownProjectError


@beartype
class ProjectIndex:
    """Resolves project names under one workspace root; touches the filesystem, so callers run it off the loop."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()

    ##### PRIVATE METHODS #####

    def _resolve_named(self, name: str) -> str:
        matches = sorted({path for path in (*self._root.glob(name), *self._root.glob(f"*/{name}")) if path.is_dir()})
        match matches:
            case [only]:
                return str(only)
            case []:
                near = sorted(path.name for path in self._root.glob(f"*/*{name}*") if path.is_dir())[:8]
                raise UnknownProjectError(name, tuple(near))
            case many:
                raise AmbiguousProjectError(name, tuple(str(path) for path in many))

    ############################################################

    ##### PUBLIC #####

    @property
    def root(self) -> str:
        return str(self._root)

    def resolve(self, project: str) -> str:
        """The project's directory: a path as given (home expanded), a short name looked up under the root."""
        match project.strip():
            case "":
                return str(self._root)
            case path if "/" in path or path.startswith("~"):
                return str(Path(path).expanduser())
            case name:
                return self._resolve_named(name)
