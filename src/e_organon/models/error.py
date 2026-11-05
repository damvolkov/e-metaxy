"""e_organon.models.error: how a tool refuses — typed, so a stream says why and a batch answers with the same reason."""

from e_organon.models.flow import Failed


##### ERRORS #####
class OrganonError(Exception):
    """A refusal the caller can act on: a bad argument, a file it may not read — never a bug."""


class OutsideRootsError(OrganonError):
    """The path sits under none of ORGANON_ROOTS, or does not exist."""


class ImageTooLargeError(OrganonError):
    """The image has more pixels than the service decodes: refused from its header, before a pixel is read."""


class FieldNotFoundError(OrganonError, LookupError):
    """The PDF has no form field of that full name."""


class AnchorNotFoundError(OrganonError, LookupError):
    """The text is on no page of the PDF — or not that many times."""


class TemplateNotFoundError(OrganonError, LookupError):
    """No template of that name among the ones the deployment keeps and the ones shipped."""


class PageNotFoundError(OrganonError, LookupError):
    """The PDF has no page of that number (from 0)."""


class UnknownJobError(OrganonError, LookupError):
    """No job under that id: never submitted, or long settled and gone."""

    def __init__(self, job: str) -> None:
        super().__init__(f"unknown job {job!r}")


class UnknownToolError(OrganonError, LookupError):
    """No tool of that name runs as a job: it does not exist, or it answers at once (tekton, organon)."""

    def __init__(self, tool: str) -> None:
        super().__init__(f"no tool {tool!r} runs as a job")


class FlowError(Exception):
    """A batch run whose workflow ended in `Failed`: carries it, so the batch answer is the streamed one."""

    def __init__(self, failed: Failed) -> None:
        super().__init__(f"{failed.kind}: {failed.reason}")
        self.failed = failed
