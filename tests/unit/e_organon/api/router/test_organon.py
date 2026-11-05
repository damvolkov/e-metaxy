"""tests/unit/e_organon/api/router/organon: organon/find over REST — a key, the tools that answer, streamed or batched."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from litestar.testing import TestClient

SSE = {"accept": "text/event-stream"}


def test_organon_find_needs_a_key(client: TestClient) -> None:
    assert client.post("/organon/find", json={"query": "merge"}).status_code == 401


def test_organon_find_batch_ranks_the_tools(client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/organon/find", json={"query": "merge pdfs", "section": "doc"}, headers=ana_key)
    first = response.json()["tools"][0]
    assert (response.status_code, first["name"], sorted(first)) == (200, "doc_merge", ["description", "name", "schema"])


def test_organon_find_streams_its_step(client: TestClient, ana_key: dict[str, str]) -> None:
    with client.stream("POST", "/organon/find", json={"query": "merge"}, headers=ana_key | SSE) as response:
        body = "".join(response.iter_text())
    assert (body.count("event: step"), "event: done" in body) == (1, True)


def test_organon_find_is_no_job_and_ignores_the_preference(client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/organon/find", json={"query": "merge"}, headers=ana_key | {"prefer": "respond-async"})
    assert (response.status_code, "tools" in response.json()) == (200, True)


def test_organon_submit_queues_the_tool_and_answers_its_job(
    client: TestClient, ana_key: dict[str, str], vault: Path
) -> None:
    response = client.post(
        "/organon/submit", json={"tool": "doc/convert", "input": {"path": str(vault / "plan.md")}}, headers=ana_key
    )
    job = client.get(f"/jobs/{response.json()['job']}", headers=ana_key)
    assert (response.status_code, response.headers["location"], job.json()["kind"]) == (
        202,
        f"/jobs/{response.json()['job']}",
        "doc/convert",
    )


def test_organon_submit_input_that_misses_the_struct_is_422(client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/organon/submit", json={"tool": "doc/convert", "input": {"path": 3}}, headers=ana_key)
    assert response.status_code == 422
