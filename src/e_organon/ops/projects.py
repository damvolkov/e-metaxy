"""ops/projects: a project by the name a person says — `e-voice` — or by its path.

A short name is looked up one and two levels under the workspace root (`~/workspaces/<name>`,
`~/workspaces/<owner>/<name>`); anything with a slash or a `~` is already a path. An unknown or ambiguous
name is a typed refusal that lists what it could have meant, so an agent can ask or retry."""

from pathlib import Path

from e_organon.infra.errors import OpsError


##### ERRORS #####
class UnknownProjectError(OpsError):
    """No project of that name lives under the workspace root."""

    def __init__(self, project: str, near: tuple[str, ...]) -> None:
        hint = f"; close: {', '.join(near)}" if near else ""
        super().__init__(f"no project named {project!r} under the workspace{hint}")
        self.project = project


class AmbiguousProjectError(OpsError):
    """More than one project carries that name: the caller must pick a path."""

    def __init__(self, project: str, paths: tuple[str, ...]) -> None:
        super().__init__(f"{project!r} names several projects: {', '.join(paths)}; pass one of these paths")
        self.project = project


##### OPS #####
class NamedProjects:
    """Resolves project names under one workspace root; touches the filesystem, so callers run it off the loop."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()

    ##### PRIVATE #####

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
