"""tests/unit/e_organon/api/router/doc: one route, two readings — JSON in batch, server-sent events when asked for."""

PATH = {"path": "/etc/hostname"}
SSE = {"accept": "text/event-stream"}


def test_doc_convert_needs_a_key(client) -> None:
    assert client.post("/doc/convert", json=PATH).status_code == 401


def test_doc_convert_batch_refuses_with_the_reason(client, root_key) -> None:
    response = client.post("/doc/convert", json=PATH, headers=root_key)
    assert (response.status_code, "/etc/hostname" in response.json()["detail"]) == (422, True)


def test_doc_convert_streams_its_events(client, root_key) -> None:
    with client.stream("POST", "/doc/convert", json=PATH, headers=root_key | SSE) as response:
        body = "".join(response.iter_text())
    assert (response.status_code, body.count("event: step"), "event: failed" in body) == (200, 1, True)
