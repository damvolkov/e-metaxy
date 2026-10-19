"""core.lifespan.services: assemble the engines both doors share — crypto, the authority, the bridge, the converters.

They are in-process objects built over the open edges; the bridge alone owns a resource (the task group every
run lives in), so it enters here and drains on shutdown. The authority refuses to exist without an owner:
a bridge nobody can approve clients for does not start."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass

import anyio
from litestar import Litestar

from e_metaxy.adapters.passphrase import PassphraseAdapter
from e_metaxy.core.crypto import Crypto
from e_metaxy.core.lifespan.adapters import AdaptersState
from e_metaxy.core.lifespan.state import AppState
from e_metaxy.core.logger import logger
from e_metaxy.core.settings import settings as st
from e_metaxy.core.settings.authority import AuthoritySettings
from e_metaxy.logic.authority import Authority
from e_metaxy.logic.bridge import Bridge
from e_metaxy.logic.converters import Converters
from e_metaxy.logic.eng import EngDesk
from e_metaxy.logic.ports import OwnerPort
from e_metaxy.logic.projects import ProjectIndex
from e_metaxy.models.auth import Policy
from e_metaxy.models.error import OwnerUnsetError
from e_metaxy.models.profile import Profile
from e_metaxy.processors.doc import DocProcessor
from e_metaxy.processors.md import MDProcessor


##### SECTION #####
@dataclass(frozen=True, slots=True)
class ServicesState:
    """The typed services section: the signing engine, the token policy, and the engines the doors call."""

    crypto: Crypto
    policy: Policy
    authority: Authority
    bridge: Bridge
    desk: EngDesk
    converters: Converters
    profiles: Mapping[str, Profile]


def owner(crypto: Crypto, conf: AuthoritySettings) -> OwnerPort:
    """The owner who approves clients; the bridge refuses to start without one."""
    match conf.owner_hash:
        case None:
            raise OwnerUnsetError
        case hashed:
            return PassphraseAdapter(crypto, hashed.get_secret_value())


def policy(conf: AuthoritySettings) -> Policy:
    """Everything the authority needs from its settings, the owner's hash excepted: that goes to the owner alone."""
    return Policy(
        issuer=conf.issuer,
        access_ttl=conf.access_ttl,
        refresh_ttl=conf.refresh_ttl,
        code_ttl=conf.code_ttl,
        consent_ttl=conf.consent_ttl,
        attempts=conf.attempts,
    )


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Build the engines over the open edges, enter the bridge, then mount the section under `system.services`."""
    system, conf = AppState.of(app).system, st.metaxy
    edges: AdaptersState = system.adapters
    crypto, rules = Crypto(st.crypto), policy(st.authority)
    profiles = Profile.book(await anyio.Path(conf.profiles.expanduser()).read_bytes())
    projects = ProjectIndex(conf.workspaces)
    bridge = Bridge(
        coders={edges.coder.kind: edges.coder},
        notifiers=edges.callers,
        ledger=edges.store,
        profiles=profiles,
        projects=projects,
        limit=conf.limit,
    )
    services = ServicesState(
        crypto=crypto,
        policy=rules,
        authority=Authority(crypto=crypto, store=edges.store, owner=owner(crypto, st.authority), policy=rules),
        bridge=bridge,
        desk=EngDesk(bridge, projects),
        converters=Converters(MDProcessor(edges.md), DocProcessor(edges.doc)),
        profiles=profiles,
    )
    async with services.bridge:
        system.services = services
        logger.info("services ready", profiles=sorted(profiles), step="START")
        yield
