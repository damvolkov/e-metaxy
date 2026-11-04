"""e_organon.models.error: how a tool refuses — typed, so a stream says why and a batch answers with the same reason."""

from e_organon.models.flow import Failed


##### ERRORS #####
class OrganonError(Exception):
    """A refusal the caller can act on: a bad argument, a file it may not read — never a bug."""


class OutsideRootsError(OrganonError):
    """The path sits under none of ORGANON_ROOTS, or does not exist."""


class FlowError(Exception):
    """A batch run whose workflow ended in `Failed`: carries it, so the batch answer is the streamed one."""

    def __init__(self, failed: Failed) -> None:
        super().__init__(f"{failed.kind}: {failed.reason}")
        self.failed = failed
