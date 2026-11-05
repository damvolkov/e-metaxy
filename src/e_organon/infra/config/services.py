"""infra/config/services: the services cluster — organon's own knobs, one `### NAME` block per service.

UPPERCASE typed fields, the field name the environment variable itself, read once at the composition root and handed
down as plain arguments."""

from pathlib import Path

from pydantic import PositiveInt

from e_organon.infra.config.base import BaseSettings


##### SETTINGS #####
class ServiceSettings(BaseSettings):
    """The canonical tools' configuration."""

    ##### DATA #####

    ### DATA — organon's own state, one subtree per section (`doc/models/tessdata`…): what a section downloads lands
    ### here once and is reused by every later start. The image sets `/data`, a volume.
    ORGANON_DATA: Path = Path("data")

    ##### FILES #####

    ### ROOTS — where a tool's path argument may point: the vault (mounted at its own path in every harness, Hermes'
    ### upload cache included) and the workspaces.
    ORGANON_ROOTS: tuple[Path, ...] = (Path("~/.config/memory"), Path("~/workspaces"))
    ### OUTBOX — where a tool's output files land, content-addressed: inside a root, so an output is the next input.
    ORGANON_OUTBOX: Path = Path("~/.config/memory/workflow/organon")

    ##### JOBS #####

    ### SLOTS — how many jobs of a section run at once, fleet-wide on the durable queue; one per section that has jobs.
    ORGANON_SLOTS_DOC: PositiveInt = 2

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
