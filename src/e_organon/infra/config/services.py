"""infra/config/services: the services cluster — organon's own knobs, one `### NAME` block per service.

The new settings doctrine (proj-py-layout `settings.md`): UPPERCASE typed fields, the field name the environment
variable itself, read once at the composition root and handed down as plain arguments. The materialized common still
reads its own scopes; it follows when e-arkhetypo's common migrates."""

from pathlib import Path

from pydantic import PositiveInt

from e_organon.infra.config.base import BaseSettings


##### SETTINGS #####
class ServiceSettings(BaseSettings):
    """The canonical tools' configuration."""

    ##### FILES #####

    ### ROOTS — where a tool's path argument may point: the vault (mounted at its own path in every harness, Hermes'
    ### upload cache included) and the workspaces.
    ORGANON_ROOTS: tuple[Path, ...] = (Path("~/.config/memory"), Path("~/workspaces"))
    ### OUTBOX — where a tool's output files land, content-addressed: inside a root, so an output is the next input.
    ORGANON_OUTBOX: Path = Path("~/.config/memory/workflow/organon")

    ##### TEKTON #####

    ### PROFILES — the nomos of the bridge, a YAML book read once at startup: what a caller may make a coder do, by name.
    ### Unset, the bridge is off: no coder, no `tekton/` tools — the public image runs the tools alone.
    TEKTON_PROFILES: Path | None = None
    ### WORKSPACES — the root a project's short name is looked up under (`e-voice` → `<root>/<owner>/e-voice`).
    TEKTON_WORKSPACES: Path = Path("~/workspaces")
    ### LIMIT — how many coder runs may be in flight at once; the rest wait their turn.
    TEKTON_LIMIT: PositiveInt = 4
    ### CLAUDE — the Claude Code CLI the coder runs and reaches live sessions through (a name on PATH, or a path).
    TEKTON_CLAUDE: str = "claude"
