"""e_metaxy.models.error: the bridge's typed failures — one root, one class per refused target."""

from core.errors import CoreError


##### ROOT #####
class MetaxyError(CoreError):
    """Every refusal of the bridge: the MCP edge turns it into a tool error, never a crash."""


##### LOOKUP #####
class UnknownTaskError(MetaxyError):
    """No task carries this id."""

    def __init__(self, task: str) -> None:
        super().__init__(f"unknown task {task!r}")
        self.task = task


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
