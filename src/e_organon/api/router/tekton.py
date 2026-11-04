"""api.router.tekton: the tekton/ section — one route per canonical tool, each streamed or batched by the request's Accept.

A handler only hands the request and its arguments to the tool's workflow on the sealed graph
(`graph.services.tekton.<tool>`); `api.stream` decides the reading. The MCP twins (`mcp/tools/tekton`) are these
handlers. A refusal of the bridge is the tool's `Failed`, so a stream says why and a batch answers 422 `kind: reason`."""

from typing import Any, Final

from litestar import Request, post
from litestar.di import NamedDependency, Provide
from litestar.handlers import HTTPRouteHandler
from litestar.params import JSONBody

from e_organon.api.deps import DepKey, graph
from e_organon.api.security import SECURITY
from e_organon.api.stream import answer
from e_organon.infra.auth.guard import OPT
from e_organon.infra.auth.models import Access
from e_organon.infra.state import State
from e_organon.models.tekton import (
    CancelIn,
    CatalogIn,
    EngIn,
    FindIn,
    PeersIn,
    ReadIn,
    SendIn,
    StartIn,
    StatusIn,
    TasksIn,
    UpdateIn,
)

TOOL_DEPS: Final[dict[str, Provide]] = {DepKey.GRAPH.value: Provide(graph, sync_to_thread=False)}


##### HANDLERS #####
async def eng(data: JSONBody[EngIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/eng: an `eng` order, the grammar parsed here."""
    return await answer(request, graph.services.tekton.eng, data)


async def start(data: JSONBody[StartIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/start: a prompt run in Claude Code, in the background."""
    return await answer(request, graph.services.tekton.start, data)


async def status(data: JSONBody[StatusIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/status: a task, held until it ends when asked to wait."""
    return await answer(request, graph.services.tekton.status, data)


async def tasks(data: JSONBody[TasksIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/tasks: the newest tasks."""
    return await answer(request, graph.services.tekton.tasks, data)


async def cancel(data: JSONBody[CancelIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/cancel: a running task interrupted."""
    return await answer(request, graph.services.tekton.cancel, data)


async def catalog(data: JSONBody[CatalogIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/catalog: the commands, skills and agents Claude Code offers in a project."""
    return await answer(request, graph.services.tekton.catalog, data)


async def find(data: JSONBody[FindIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/find: recorded sessions."""
    return await answer(request, graph.services.tekton.find, data)


async def read(data: JSONBody[ReadIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/read: a session and where it stopped."""
    return await answer(request, graph.services.tekton.read, data)


async def update(data: JSONBody[UpdateIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/update: a session renamed or tagged."""
    ### `update` is a method of `State` (a mapping): the node is read by key, never by attribute.
    return await answer(request, graph.services.tekton["update"], data)


async def peers(data: JSONBody[PeersIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/peers: the sessions open in a terminal."""
    return await answer(request, graph.services.tekton.peers, data)


async def send(data: JSONBody[SendIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """tekton/send: a message to an open session."""
    return await answer(request, graph.services.tekton.send, data)


##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = tuple(
    post(
        f"/tekton/{handler.__name__}",
        name=f"tekton.{handler.__name__}",
        status_code=200,
        tags=["tekton"],
        opt=OPT[Access.USER],
        security=SECURITY,
        dependencies=TOOL_DEPS,
    )(handler)
    for handler in (eng, start, status, tasks, cancel, catalog, find, read, update, peers, send)
)
