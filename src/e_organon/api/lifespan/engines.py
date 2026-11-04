"""api.lifespan.engines: build the engines over the providers' ports, then survey every provider once.

The concern owns its subtree as a typed section: `EnginesState` holds each engine by its role. The engines keep
references and configuration only — but the bridge, which owns the group its runs live in: it enters on an exit stack,
and every run still going is cancelled when the app stops. `auth` is the engine every door asks who is calling (the
token middleware reads it off the sealed graph); with a secret set its admin account is made here, no key issued. `health` surveys every provider at once (each under PING_TIMEOUT, so the whole takes the slowest): right
after they open — one log event each, never a failed start — and on every `GET /ready`. Required are `store`, the
provider the app's records live on, and `auth`, without which no key resolves; every other provider is reported, never
blocking."""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Final

import anyio
from litestar import Litestar

from e_organon.api.lifespan.providers import ProvidersState
from e_organon.api.state import AppState
from e_organon.engines.artifact import ArtifactEngine
from e_organon.engines.auth import AuthEngine
from e_organon.engines.bridge import BridgeEngine
from e_organon.engines.health import HealthEngine
from e_organon.infra.logger import logger
from e_organon.infra.settings import settings as st
from e_organon.ops.projects import NamedProjects
from e_organon.ports.coder import Profile

### the providers a ready service cannot do without; a role not here is optional.
REQUIRED: Final[frozenset[str]] = frozenset({"store", "auth"})


##### SECTION #####
@dataclass(frozen=True, slots=True)
class EnginesState:
    """The typed engines section: `auth`, accounts and keys; `health`, every provider surveyed together, the required
    ones deciding readiness."""

    auth: AuthEngine
    health: HealthEngine
    artifact: ArtifactEngine
    bridge: BridgeEngine


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Build the engines over the mounted providers, mount them under `system.engines`, log the startup survey."""
    system = AppState.of(app).system
    providers: ProvidersState = system.providers
    conf, services = st.engines.auth, st.services
    async with AsyncExitStack() as stack:
        ### the profile book is read once, here: a profile changes with a restart, never under a running task.
        book = Profile.book(await (await anyio.Path(services.TEKTON_PROFILES).expanduser()).read_bytes())
        bridge = BridgeEngine(
            coders={providers.coder.kind: providers.coder},
            ledger=providers.store,
            profiles=book,
            projects=NamedProjects(services.TEKTON_WORKSPACES),
            limit=services.TEKTON_LIMIT,
        )
        engines = EnginesState(
            auth=AuthEngine(providers.auth, conf),
            health=HealthEngine(providers.named, REQUIRED),
            artifact=ArtifactEngine(services.ORGANON_OUTBOX),
            bridge=await stack.enter_async_context(bridge),
        )
        system.engines = engines
        admin = (await engines.auth.ensure()).owner if conf.secret else "closed"
        logger.info("auth ready", admin=admin, ttl=str(conf.ttl or "never"), step="START")
        _ = [
            (logger.info if verdict.ok else logger.warning)(
                "provider health", provider=verdict.name, ok=verdict.ok, required=verdict.required,
                latency_ms=verdict.latency, reason=verdict.reason, step="START",
            )
            for verdict in await engines.health.survey()
        ]  # fmt: skip
        yield
