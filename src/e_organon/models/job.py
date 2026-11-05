"""e_organon.models.job: what the jobs say — a tool run in the background, as the API and the MCP door tell it.

A job is the tool's own run, so its progress is what a stream would have told: `steps`, the `Step`s entered so far as
builtins (`step` the latest of them), and at the end `done`, the answer as builtins, or `failed`, its `kind` and `reason`."""

from datetime import datetime
from typing import Annotated, Any, Final, Self

import msgspec

from e_organon.infra.background import BackgroundJob, BackgroundState

### an MCP client gives up on a call long before a job ends: a wait is capped well under that, as tekton/status's.
WAIT_CAP: Final[float] = 25.0


##### JOBS #####
class AcceptedJob(msgspec.Struct, frozen=True, kw_only=True):
    """A tool run taken on: its job, to read at `/jobs/{job}`."""

    job: str
    state: BackgroundState


class Job(msgspec.Struct, frozen=True, kw_only=True):
    """A job as it stands: its tool (`kind`, `<section>/<word>`), where it is, its latest progress, one message per
    failed attempt, when it was made and when it settled."""

    id: str
    kind: str
    state: BackgroundState
    progress: dict[str, Any] | None
    errors: list[str]
    created: datetime
    finished: datetime | None

    @classmethod
    def of(cls, job: BackgroundJob) -> Self:
        """The queue's job as the API tells it: its arguments are the caller's, not told again."""
        return cls(
            id=job.id,
            kind=job.kind,
            state=job.state,
            progress=dict(job.progress) if job.progress is not None else None,
            errors=list(job.errors),
            created=job.created,
            finished=job.finished,
        )


##### ARGUMENTS #####
class StatusJobIn(msgspec.Struct, frozen=True, kw_only=True):
    """`job`: its id. `wait`: seconds to hold the answer until the job settles (0 answers at once; at most 25)."""

    job: str
    wait: Annotated[float, msgspec.Meta(ge=0, le=WAIT_CAP)] = 0.0


class CancelJobIn(msgspec.Struct, frozen=True, kw_only=True):
    """`job`: its id."""

    job: str
