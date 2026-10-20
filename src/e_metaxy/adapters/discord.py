"""e_metaxy.adapters.discord: tell Discord a task ended — one webhook post, no model, no agent in between.

The caller `discord` is a chat front that already spoke for the user (an `eng` order through a hook or a channel
bot): when its task ends, the outcome lands in that channel as the message the user would want to read — what
ran where, the session to continue with `eng @…`, and the result. A failed post is logged and dropped — a
callback never fails a task."""

from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType
from typing import ClassVar, Final

import structlog
import wreq
from beartype import beartype

from e_metaxy.adapters.base import BaseAdapter
from e_metaxy.models.task import Task, TaskState

log = structlog.get_logger()

MARK: Final[Mapping[TaskState, str]] = MappingProxyType(
    {
        TaskState.DONE: "✅ Claude terminó",
        TaskState.FAILED: "❌ Claude falló",
        TaskState.CANCELLED: "⏹ Claude se detuvo",
        TaskState.RUNNING: "▶ Claude sigue",
    }
)
LIMIT: Final = 2000


@beartype
class DiscordAdapter(BaseAdapter):
    """One wreq client posting to a channel webhook."""

    name: ClassVar[str] = "discord"

    __slots__ = ("_client", "_timeout", "_url")

    def __init__(self, url: str, timeout: timedelta = timedelta(seconds=10)) -> None:
        self._url = url
        self._timeout = timeout
        self._client: wreq.Client | None = None

    ##### PRIVATE METHODS #####

    @staticmethod
    def _notify_content(task: Task) -> str:
        """Head with where and which session, the outcome, and how to go on — within Discord's 2000 characters."""
        where = task.cwd.rsplit("/", 1)[-1] or "workspace"
        session = task.session[:8] or "—"
        head = f"{MARK[task.state]} · {where} · sesión `{session}` · tarea `{task.id[-8:]}`"
        tail = f"\n\n`eng @{session}: …` para seguir"
        body = (task.result or task.error or task.state.value).strip()
        room = LIMIT - len(head) - len(tail) - 2
        return f"{head}\n{body if len(body) <= room else body[: room - 1] + '…'}{tail}"

    def _common_connected(self) -> wreq.Client:
        match self._client:
            case None:
                msg = "DiscordAdapter not connected: the lifespan opens it"
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
                self._url, json={"content": self._notify_content(task), "allowed_mentions": {"parse": []}}
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — a callback boundary: the task already ended, the failure is only logged
            log.warning("DISCORD_NOTIFY_FAILED", task=task.id, error=repr(exc))
            return
        log.info("DISCORD_NOTIFIED", task=task.id, state=task.state)
