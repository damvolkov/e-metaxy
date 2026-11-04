"""api.deps: chained dependency providers — litestar resolves the graph recursively per request.

No FastAPI `Depends()` sugar: binding is by *name*. Each link declares what it consumes in its own
signature (`store` takes `graph`), every route wires the chains it uses in a local `dependencies` mapping, and the app
itself registers nothing. Links run once per request, in resolved order; independent links run concurrently.

Who may reach a route is `infra/auth/guard`'s, the same check the MCP door's tools pass; `caller` hands the user the
token middleware resolved to the handlers that take it.
"""

from enum import StrEnum, auto
from typing import Any

from litestar.connection import Request
from litestar.di import NamedDependency

from e_organon.api.state import AppState
from e_organon.engines.auth import AuthEngine
from e_organon.infra.auth.models import Caller
from e_organon.infra.state import State


##### DEPENDENCY KEYS — the wiring vocabulary: a typo is an attribute error at import, never a silent runtime miss #####
class DepKey(StrEnum):
    GRAPH = auto()
    AUTH = auto()
    CALLER = auto()


##### LINKS — each names its injection parameter and consumes other links by name #####
def graph(state: AppState) -> State:
    """Root of every chain: the app's system graph, filled by the lifespans and sealed — read off Litestar's
    reserved `state`, which Litestar builds as `AppState` itself."""
    return state.system


def auth(graph: NamedDependency[State]) -> AuthEngine:
    """Who is asking, and the accounts and keys the admin manages. Chain: graph."""
    return graph.engines.auth


def caller(request: Request[Caller, None, Any]) -> Caller:
    """Who is asking: the user the token middleware resolved, carried into the handler. Chain: request."""
    return request.user
