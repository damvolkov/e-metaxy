"""api.lifespan.engines: build the engines over the providers' ports, then survey every provider once.

The concern owns its subtree as a typed section: `EnginesState` holds each engine by its role. The engines keep
references and configuration only — but the bridge, which owns the group its runs live in: it enters on an exit stack,
and every run still going is cancelled when the app stops. `auth` is the engine every door asks who is calling (the
token middleware reads it off the sealed graph); with a secret set its admin account is made here, no key issued. `health` surveys every provider at once (each under PING_TIMEOUT, so the whole takes the slowest): right
after they open — one log event each, never a failed start — and on every `GET /ready`. Required are `store`, the
provider the app's records live on, and `auth`, without which no key resolves; every other provider is reported, never
blocking.

`dispatch` is the background work: PgQueuer on the queue's database (QUEUE_ENGINE picks the row of `QUEUES`), memory
behind it. It is built here and left open to registration; `api/lifespan/jobs` registers every kind and enters it."""

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

import anyio
from litestar import Litestar

from e_organon.api.lifespan.providers import ProvidersState
from e_organon.api.state import AppState
from e_organon.engines.artifact import ArtifactEngine
from e_organon.engines.auth import AuthEngine
from e_organon.engines.bridge import BridgeEngine
from e_organon.engines.dispatch import DispatchEngine
from e_organon.engines.health import HealthEngine
from e_organon.infra.background import Background
from e_organon.infra.config.engines import QueueEngine
from e_organon.infra.logger import logger
from e_organon.infra.settings import settings as st
from e_organon.ops.projects import NamedProjects
from e_organon.ports.coder import CoderPort, Profile
from e_organon.ports.database import DatabaseListenPort
from e_organon.ports.queue import QueuePort
from e_organon.providers.drivers.queue.pgqueuer import PgqueuerDriver

### the providers a ready service cannot do without; a role not here is optional.
REQUIRED: Final[frozenset[str]] = frozenset({"store", "auth"})

### the durable queue by engine: changing the backend is one row here, no client of the dispatch notices.
QUEUES: Final[Mapping[QueueEngine, Callable[[DatabaseListenPort], QueuePort]]] = MappingProxyType(
    {
        QueueEngine.PGQUEUER: lambda database: PgqueuerDriver(
            database,
            database,
            timeout=st.QUEUE_TIMEOUT,
            poll=st.QUEUE_POLL,
            drain=st.QUEUE_DRAIN,
            heartbeat=st.QUEUE_HEARTBEAT,
            restart=st.QUEUE_RESTART,
        )
    }
)


##### SECTION #####
@dataclass(frozen=True, slots=True)
class EnginesState:
    """The typed engines section: `auth`, accounts and keys; `health`, every provider surveyed together, the required
    ones deciding readiness."""

    auth: AuthEngine
    health: HealthEngine
    artifact: ArtifactEngine
    ### built here, entered by `api/lifespan/jobs` once every kind is registered.
    dispatch: DispatchEngine
    ### present only with the bridge on: the coder it drives opened (TEKTON_PROFILES set).
    bridge: BridgeEngine | None


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Build the engines over the mounted providers, mount them under `system.engines`, log the startup survey."""
    system = AppState.of(app).system
    providers: ProvidersState = system.providers
    async with AsyncExitStack() as stack:
        ### the profile book is read once, here: a profile changes with a restart, never under a running task.
        match providers.coder, st.TEKTON_PROFILES:
            case (CoderPort() as coder, Path() as profiles):
                book = Profile.book(await (await anyio.Path(profiles).expanduser()).read_bytes())
                bridge = await stack.enter_async_context(
                    BridgeEngine(
                        coders={coder.kind: coder},
                        ledger=providers.store,
                        profiles=book,
                        projects=NamedProjects(st.TEKTON_WORKSPACES),
                        limit=st.TEKTON_LIMIT,
                    )
                )
            case _:
                bridge = None
        engines = EnginesState(
            auth=AuthEngine(providers.auth, secret=st.AUTH_SECRET, ttl=st.AUTH_TTL, admin=st.AUTH_ADMIN),
            health=HealthEngine(providers.named, REQUIRED, st.PING_TIMEOUT),
            artifact=ArtifactEngine(st.ORGANON_OUTBOX),
            dispatch=DispatchEngine(
                QUEUES[st.QUEUE_ENGINE](providers.queue), Background(), {}, throttle=st.QUEUE_THROTTLE.total_seconds()
            ),
            bridge=bridge,
        )
        system.engines = engines
        admin = (await engines.auth.ensure()).owner if st.AUTH_SECRET else "closed"
        logger.info("auth ready", admin=admin, ttl=str(st.AUTH_TTL or "never"), step="START")
        _ = [
            (logger.info if verdict.ok else logger.warning)(
                "provider health", provider=verdict.name, ok=verdict.ok, required=verdict.required,
                latency_ms=verdict.latency, reason=verdict.reason, step="START",
            )
            for verdict in await engines.health.survey()
        ]  # fmt: skip
        yield
