"""tests/unit/e_organon/api/router/tekton: the tekton tools over HTTP on the live app and its scripted coder — a key at every
route, a task started and watched, a stream of steps while it waits, a refusal as 422 `kind: reason`."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from litestar.testing import TestClient

SSE = {"accept": "text/event-stream"}
TASK = {"prompt": "ping", "project": "/tmp", "profile": "research"}

TOOLS = {
    "eng": {"text": "eng ps"},
    "start": TASK,
    "status": {"task": "missing"},
    "tasks": {},
    "cancel": {"task": "missing"},
    "catalog": {"project": "/tmp"},
    "find": {},
    "read": {"session": "s-new"},
    "update": {"session": "s-new", "tag": "x"},
    "peers": {},
    "send": {"peer": "e-engineer-bc", "text": "hola"},
}


@pytest.mark.parametrize("tool", TOOLS)
def test_tekton_needs_a_key(client: TestClient, tool: str) -> None:
    assert client.post(f"/tekton/{tool}", json=TOOLS[tool]).status_code == 401


def test_tekton_start_then_status_waits_for_the_end(client: TestClient, ana_key: dict[str, str]) -> None:
    started = client.post("/tekton/start", json=TASK, headers=ana_key)
    task = started.json()
    status = client.post("/tekton/status", json={"task": task["id"], "wait": 5}, headers=ana_key)
    listed = client.post("/tekton/tasks", json={"state": "done", "limit": 100}, headers=ana_key)
    assert (started.status_code, task["state"], status.json()["state"], status.json()["result"]) == (
        200,
        "running",
        "done",
        "pong",
    )
    assert task["id"] in [each["id"] for each in listed.json()["tasks"]]


def test_tekton_cancel_a_finished_task_leaves_it_as_it_ended(client: TestClient, ana_key: dict[str, str]) -> None:
    task = client.post("/tekton/start", json=TASK, headers=ana_key).json()
    client.post("/tekton/status", json={"task": task["id"], "wait": 5}, headers=ana_key)
    cancelled = client.post("/tekton/cancel", json={"task": task["id"]}, headers=ana_key)
    assert (cancelled.status_code, cancelled.json()["state"]) == (200, "done")


def test_tekton_status_streams_while_it_waits(client: TestClient, ana_key: dict[str, str]) -> None:
    task = client.post("/tekton/start", json=TASK, headers=ana_key).json()
    with client.stream(
        "POST", "/tekton/status", json={"task": task["id"], "wait": 5}, headers=ana_key | SSE
    ) as response:
        body = "".join(response.iter_text())
    assert (response.status_code, body.count("event: step") >= 1, "event: done" in body) == (200, True, True)


def test_tekton_refuses_with_the_reason(client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/tekton/status", json={"task": "missing"}, headers=ana_key)
    assert (response.status_code, response.json()["detail"]) == (422, "UnknownTaskError: unknown task 'missing'")


def test_tekton_stream_ends_in_failed(client: TestClient, ana_key: dict[str, str]) -> None:
    with client.stream("POST", "/tekton/start", json=TASK | {"profile": "nope"}, headers=ana_key | SSE) as response:
        body = "".join(response.iter_text())
    assert (response.status_code, body.count("event: step"), "event: failed" in body) == (200, 1, True)


def test_tekton_refuses_what_is_out_of_bounds(client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/tekton/tasks", json={"limit": 0}, headers=ana_key)
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("tool", "answer"),
    [
        ("catalog", "commands"),
        ("find", "sessions"),
        ("peers", "peers"),
        ("read", "turns"),
        ("update", "tag"),
        ("send", "delivered"),
    ],
)
def test_tekton_answers_in_the_coders_words(
    client: TestClient, ana_key: dict[str, str], tool: str, answer: str
) -> None:
    response = client.post(f"/tekton/{tool}", json=TOOLS[tool], headers=ana_key)
    assert (response.status_code, answer in response.json()) == (200, True)


def test_tekton_eng_runs_the_grammar(client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/tekton/eng", json={"text": "eng ls", "project": "/tmp"}, headers=ana_key)
    answer = response.json()
    assert (answer["verb"], [row["session"] for row in answer["result"]][:1]) == ("list", ["s-new"])
