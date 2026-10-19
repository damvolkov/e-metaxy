"""e_metaxy.models.error: the bridge's typed failures — one root, one class per refused target."""

from e_metaxy.core.errors import CoreError


##### ROOT #####
class MetaxyError(CoreError):
    """Every refusal of the bridge: the MCP edge turns it into a tool error, never a crash."""


##### LOOKUP #####
class UnknownTaskError(MetaxyError):
    """No task carries this id."""

    def __init__(self, task: str) -> None:
        super().__init__(f"unknown task {task!r}")
        self.task = task


class UnknownSessionError(MetaxyError):
    """No project of the coder holds a session with this id."""

    def __init__(self, session: str) -> None:
        super().__init__(f"unknown session {session!r}; session_find lists them")
        self.session = session


class EmptyOrderError(MetaxyError):
    """An `eng` order with nothing after the prefix."""

    def __init__(self) -> None:
        super().__init__("empty order; try `eng <project>: <order>`, `eng @<session>: <order>`, `eng ls` or `eng ps`")


class AmbiguousSessionError(MetaxyError):
    """A prefix or title that matches more than one session: the caller must pass a longer one."""

    def __init__(self, session: str, matches: tuple[str, ...]) -> None:
        super().__init__(f"{session!r} matches several sessions: {', '.join(matches)}; pass one of these ids")
        self.session = session


class UnknownProfileError(MetaxyError):
    """The caller named a profile the book does not declare."""

    def __init__(self, profile: str, known: tuple[str, ...]) -> None:
        super().__init__(f"unknown profile {profile!r}; declared: {', '.join(known) or 'none'}")
        self.profile = profile


class UnknownCoderError(MetaxyError):
    """A profile points at a coder no adapter serves."""

    def __init__(self, coder: str) -> None:
        super().__init__(f"no coder serves {coder!r}")
        self.coder = coder


class UnknownConsentError(MetaxyError):
    """No pending authorization carries this id: it never existed, was decided, or expired."""

    def __init__(self, request: str) -> None:
        super().__init__("this authorization request is unknown or expired; start the sign-in again")
        self.request = request


class UnknownProjectError(MetaxyError):
    """No project of that name lives under the workspace root."""

    def __init__(self, project: str, near: tuple[str, ...]) -> None:
        hint = f"; close: {', '.join(near)}" if near else ""
        super().__init__(f"no project named {project!r} under the workspace{hint}")
        self.project = project


class AmbiguousProjectError(MetaxyError):
    """More than one project carries that name: the caller must pick a path."""

    def __init__(self, project: str, paths: tuple[str, ...]) -> None:
        super().__init__(f"{project!r} names several projects: {', '.join(paths)}; pass one of these paths")
        self.project = project


##### SETUP #####
class OwnerUnsetError(MetaxyError):
    """The bridge refuses to start without an owner: no client could ever be approved."""

    def __init__(self) -> None:
        super().__init__("no owner: run `e-metaxy owner` and set METAXY_AUTH_OWNER_HASH to the hash it prints")


##### POLICY #####
class RootDeniedError(MetaxyError):
    """The working directory lies outside every root the profile allows."""

    def __init__(self, cwd: str, profile: str) -> None:
        super().__init__(f"cwd {cwd!r} is outside the roots of profile {profile!r}")
        self.cwd = cwd


class TaskStateError(MetaxyError):
    """A transition the task lifecycle does not allow."""

    def __init__(self, task: str, source: str, target: str) -> None:
        super().__init__(f"task {task!r} cannot move {source} → {target}")
        self.task = task
