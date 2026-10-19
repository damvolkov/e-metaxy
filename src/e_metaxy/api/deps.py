"""api.deps: chained dependency providers — litestar resolves the graph per request, binding by *name*.

Each link declares what it consumes in its own signature (`converters` and `authority` take `graph`), every
route wires the chains it uses in a local `dependencies` mapping, and the app itself registers nothing. The
graph is the one the MCP door reads too: the same sealed singletons serve both."""

from enum import StrEnum, auto

from litestar.di import NamedDependency

from e_metaxy.core.lifespan.state import AppState
from e_metaxy.core.state import State
from e_metaxy.logic.authority import Authority
from e_metaxy.logic.converters import Converters


##### DEPENDENCY KEYS — the wiring vocabulary: a typo is an attribute error at import, never a silent runtime miss #####
class DepKey(StrEnum):
    GRAPH = auto()
    CONVERTERS = auto()
    AUTHORITY = auto()


##### LINKS — each names its injection parameter and consumes other links by name #####
def graph(state: AppState) -> State:
    """Root of every chain: the app's system graph, filled by the lifespans and sealed."""
    return state.system


def converters(graph: NamedDependency[State]) -> Converters:
    """The façade over the Markdown renderer and the deep reader. Chain: graph."""
    return graph.services.converters


def authority(graph: NamedDependency[State]) -> Authority:
    """The authorization server: consent, tokens, verification. Chain: graph."""
    return graph.services.authority
