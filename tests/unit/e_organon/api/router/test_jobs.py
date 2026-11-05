"""tests/unit/e_organon/api/router/jobs: a tool asked to answer later is a job — taken on with 202 and a `Location`, read
at `/jobs/{id}`, followed by server-sent events until it settles, stopped by a DELETE; the same answer as the batch."""

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from litestar.testing import TestClient

ASYNC = {"prefer": "respond-async"}
SSE = {"accept": "text/event-stream"}


def events(body: str) -> list[tuple[str, dict]]:
    """A server-sent body as its (event, data) pairs, the keep-alive comments left out."""
    blocks = [block for block in body.replace("\r\n", "\n").split("\n\n") if "event:" in block]
    return [
        (
            next(line.removeprefix("event: ") for line in block.splitlines() if line.startswith("event: ")),
            json.loads(next(line.removeprefix("data: ") for line in block.splitlines() if line.startswith("data: "))),
        )
        for block in blocks
    ]


def test_jobs_convert_in_the_background_is_the_batch_answer(
    vault: Path, client: TestClient, root_key: dict[str, str]
) -> None:
    body = {"path": str(vault / "plan.md")}
    batch = client.post("/doc/convert", json=body, headers=root_key)
    taken = client.post("/doc/convert", json=body, headers=root_key | ASYNC)
    job = taken.json()["job"]
    with client.stream("GET", f"/jobs/{job}/events", headers=root_key) as response:
        told = events("".join(response.iter_text()))
    settled = client.get(f"/jobs/{job}", headers=root_key).json()
    assert (batch.status_code, taken.status_code, taken.headers["location"], taken.json()["state"]) == (
        200,
        202,
        f"/jobs/{job}",
        "available",
    )
    assert taken.headers["preference-applied"] == "respond-async"
    assert [(name, data.get("name")) for name, data in told[:-1]] == [("step", "resolve"), ("step", "read")]
    assert told[-1] == ("done", {"type": "done", "result": batch.json()})
    assert (settled["state"], settled["kind"], settled["errors"], settled["progress"]["done"]) == (
        "completed",
        "doc/convert",
        [],
        batch.json(),
    )


def test_jobs_failed_in_the_background_says_why(client: TestClient, root_key: dict[str, str]) -> None:
    job = client.post("/doc/convert", json={"path": "/etc/hostname"}, headers=root_key | ASYNC).json()["job"]
    with client.stream("GET", f"/jobs/{job}/events", headers=root_key) as response:
        told = events("".join(response.iter_text()))
    settled = client.get(f"/jobs/{job}", headers=root_key).json()
    assert (told[-1][0], told[-1][1]["kind"]) == ("failed", "OutsideRootsError")
    assert (settled["state"], settled["progress"]["failed"]["kind"]) == ("failed", "OutsideRootsError")


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({"prefer": "respond-async, wait=5"}, 202),
        ({"Prefer": "Respond-Async"}, 202),
        ({"prefer": "wait=5; respond-async"}, 200),
        ({"prefer": "return=minimal"}, 200),
        ({"prefer": "respond-async", "accept": "text/event-stream"}, 202),
    ],
    ids=["with-params", "case", "param-is-not-a-token", "other-preference", "beats-sse"],
)
def test_jobs_prefer_is_read_as_rfc_7240(
    vault: Path, client: TestClient, root_key: dict[str, str], headers: dict[str, str], status: int
) -> None:
    response = client.post("/doc/convert", json={"path": str(vault / "plan.md")}, headers=root_key | headers)
    assert response.status_code == status


def test_jobs_a_tool_that_is_no_job_ignores_the_preference(client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/tekton/tasks", json={"limit": 1}, headers=ana_key | ASYNC)
    assert (response.status_code, "tasks" in response.json()) == (200, True)


def test_jobs_cancel_of_a_settled_job_leaves_it_as_it_is(
    vault: Path, client: TestClient, root_key: dict[str, str]
) -> None:
    job = client.post("/doc/convert", json={"path": str(vault / "plan.md")}, headers=root_key | ASYNC).json()["job"]
    with client.stream("GET", f"/jobs/{job}/events", headers=root_key) as response:
        _ = "".join(response.iter_text())
    stopped = client.delete(f"/jobs/{job}", headers=root_key)
    assert (stopped.status_code, stopped.json()["state"]) == (200, "completed")


@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/jobs/nope"), ("GET", "/jobs/nope/events"), ("DELETE", "/jobs/nope")]
)
def test_jobs_unknown_job_is_404(client: TestClient, root_key: dict[str, str], method: str, path: str) -> None:
    response = client.request(method, path, headers=root_key)
    assert (response.status_code, response.json()["detail"]) == (404, "unknown job 'nope'")


@pytest.mark.parametrize(("method", "path"), [("GET", "/jobs/1"), ("GET", "/jobs/1/events"), ("DELETE", "/jobs/1")])
def test_jobs_need_a_key(client: TestClient, method: str, path: str) -> None:
    assert client.request(method, path).status_code == 401
