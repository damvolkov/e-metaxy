"""e_metaxy.adapters.notifier.openhuman: tell OpenHuman a task ended — its core's own trigger, over JSON-RPC.

`openhuman.webhooks_trigger_agent` runs OpenHuman's triage pipeline on the payload: the polymath reads the
outcome and decides what to do with it. A failed call is logged and dropped — a callback never fails a task."""

from datetime import timedelta
from itertools import count
from typing import ClassVar, Final

import msgspec
import structlog
import wreq
from beartype import beartype

from adapters.base import BaseAdapter
from e_metaxy.models.task import Task

log = structlog.get_logger()

METHOD: Final = "openhuman.webhooks_trigger_agent"


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

    def _notify_body(self, task: Task) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": next(self._ids),
            "method": METHOD,
            "params": {
                "caller_id": f"e-metaxy:{task.id}",
                "source": "external",
                "reason": f"e-metaxy task {task.state}: {task.prompt[:120]}",
                "payload": msgspec.to_builtins(task, enc_hook=Task.enc_hook),
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
