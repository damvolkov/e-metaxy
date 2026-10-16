"""e_metaxy.adapters.notifier.openhuman: tell OpenHuman a task ended — its core's own trigger, over JSON-RPC.

`openhuman.webhooks_trigger_agent` runs OpenHuman's triage pipeline: the classifier sees only the envelope's
label and the **payload**, never the reason — so the order ("send Damien the result") and the outcome to
deliver ride in the payload, and the reason stays a record label. A failed call is logged and dropped —
a callback never fails a task."""

from collections.abc import Mapping
from datetime import timedelta
from itertools import count
from types import MappingProxyType
from typing import ClassVar, Final

import msgspec
import structlog
import wreq
from beartype import beartype

from e_metaxy.adapters.base import BaseAdapter
from e_metaxy.models.task import Task, TaskState

log = structlog.get_logger()

METHOD: Final = "openhuman.webhooks_trigger_agent"
ACTION: Final[Mapping[TaskState, str]] = MappingProxyType(
    {
        TaskState.DONE: "send Damien the result on Discord",
        TaskState.FAILED: "tell Damien the task failed and why",
        TaskState.CANCELLED: "tell Damien the task was cancelled",
        TaskState.RUNNING: "note that the engineer is still working",
    }
)


@beartype
class OpenHumanNotifier(BaseAdapter):
    """One wreq client against the OpenHuman core's `/rpc`, authenticated with its core token."""

    name: ClassVar[str] = "openhuman"

    __slots__ = ("_client", "_ids", "_timeout", "_token", "_url")

    def __init__(self, url: str, token: str, timeout: timedelta = timedelta(seconds=10)) -> None:
        self._url = url
        self._token = token
        self._timeout = timeout
        self._ids = count(1)
        self._client: wreq.Client | None = None

    ##### PRIVATE METHODS #####

    @staticmethod
    def _notify_reason(task: Task) -> str:
        """The envelope's record label — the classifier never sees it; the payload carries the order."""
        return f"e-metaxy task {task.state}: {task.prompt[:120]}"

    @staticmethod
    def _notify_payload(task: Task) -> dict[str, object]:
        """The only text triage reads: the instruction first, then the outcome to act with, then the whole truth."""
        outcome = (task.result or task.error or task.state.value)[:300]
        return {
            "instruction": f"an engineer finished a task for Damien — {ACTION[task.state]}. Outcome: {outcome}",
            "task": msgspec.to_builtins(task, enc_hook=Task.enc_hook),
        }

    def _notify_body(self, task: Task) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": next(self._ids),
            "method": METHOD,
            "params": {
                "caller_id": f"e-metaxy:{task.id}",
                "source": "external",
                "reason": self._notify_reason(task),
                "payload": self._notify_payload(task),
            },
        }

    def _common_connected(self) -> wreq.Client:
        match self._client:
            case None:
                msg = "OpenHumanNotifier not connected: the lifespan opens it"
                raise RuntimeError(msg)
            case client:
                return client

    ############################################################

    ##### LIFECYCLE #####

    async def connect(self) -> None:
        self._client = wreq.Client(timeout=self._timeout)

    async def close(self) -> None:
        match self._client:
            case None:
                return
            case client:
                client.close()
                self._client = None

    ##### PUBLIC #####

    async def notify(self, task: Task) -> None:
        try:
            response = await self._common_connected().post(
                self._url, json=self._notify_body(task), bearer_auth=self._token
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — a callback boundary: the task already ended, the failure is only logged
            log.warning("OPENHUMAN_NOTIFY_FAILED", task=task.id, error=repr(exc))
            return
        log.info("OPENHUMAN_NOTIFIED", task=task.id, state=task.state)
