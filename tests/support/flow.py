"""tests/support/flow: the shapes of the tool-run fixtures — a workflow played to its end, read as the names of its steps and
either its answer (`Answered`) or the kind of the error it failed with (`Refused`)."""

from collections.abc import Callable, Coroutine
from typing import Any

from e_organon.services.flow import ToolFlow

type Answered = Callable[[ToolFlow[Any, Any], Any], Coroutine[None, None, tuple[list[str], Any]]]
type Refused = Callable[[ToolFlow[Any, Any], Any], Coroutine[None, None, tuple[list[str], str]]]
