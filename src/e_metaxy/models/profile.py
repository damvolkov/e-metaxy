"""e_metaxy.models.profile: the nomos of the bridge — what a caller may make a coder do, by name.

A caller picks a profile and never passes flags. The permission mode is a closed enum: `bypassPermissions`
is not a member, so a book that asks for it fails to load instead of reaching a coder."""

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import msgspec

from core.struct import CheckedStruct


##### ENUMS #####
class CoderKind(StrEnum):
    """The engineer harnesses the bridge can drive."""

    CLAUDE = "claude"
    OPENCODE = "opencode"


class ProfileMode(StrEnum):
    """How the coder treats a tool outside `allow`: ask nobody and deny, accept edits, plan only, or decide."""

    DEFAULT = "default"
    DONT_ASK = "dontAsk"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    AUTO = "auto"


##### MODEL #####
class Profile(CheckedStruct, frozen=True, kw_only=True):
    """One named policy: coder, permission mode, tools, the roots a task may run under, and its limits."""

    name: str = ""
    coder: CoderKind = CoderKind.CLAUDE
    mode: ProfileMode = ProfileMode.DONT_ASK
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    roots: tuple[str, ...] = ()
    turns: int | None = None
    budget: float | None = None
    model: str | None = None
    note: str = ""

    def admits(self, cwd: Path) -> bool:
        """Whether `cwd` lives under one of the roots; a profile without roots admits nothing."""
        target = cwd.expanduser().resolve()
        return any(target.is_relative_to(Path(root).expanduser().resolve()) for root in self.roots)

    @classmethod
    def book(cls, raw: bytes) -> Mapping[str, Profile]:
        """Every profile of a YAML book, keyed by name and named after its key — frozen."""
        decoded = msgspec.yaml.decode(raw, type=dict[str, dict[str, object]])
        return MappingProxyType({name: cls.convert({**fields, "name": name}, cls) for name, fields in decoded.items()})
