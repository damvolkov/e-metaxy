"""tests/unit/e_organon/api/router/doc: one route, two readings — JSON in batch, server-sent events when asked for."""

from typing import TYPE_CHECKING

import anyio
import pytest

from support.pdf import placements

if TYPE_CHECKING:
    from pathlib import Path

    from litestar.testing import TestClient

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


def test_a_key_nobody_holds_is_refused_where_keys_are_read(client) -> None:
    """A public route never reads the key; a tool's is refused before the tool runs."""
    forged = {"Authorization": "Bearer stolen"}
    answered = [
        client.post("/doc/convert", json=PATH, headers=forged).status_code,
        client.get("/auth/me", headers=forged).status_code,
        client.get("/health", headers=forged).status_code,
    ]
    assert answered == [401, 401, 200]


@pytest.mark.parametrize(
    ("tool", "body"),
    [
        ("inspect", {"path": "/etc/hostname"}),
        ("merge", {"paths": ["/etc/hostname", "/etc/hosts"]}),
        ("split", {"path": "/etc/hostname", "ranges": [[0, 0]]}),
        ("fill", {"path": "/etc/hostname", "values": {"a": "b"}}),
        ("render", {"path": "/etc/hostname"}),
    ],
)
def test_doc_tools_refuse_a_path_outside_the_roots(client, root_key, tool: str, body: dict) -> None:
    response = client.post(f"/doc/{tool}", json=body, headers=root_key)
    assert (response.status_code, response.json()["detail"].startswith("OutsideRootsError")) == (422, True)


async def test_doc_stamp_and_signature_over_rest(vault: Path, client: TestClient, ana_key: dict[str, str]) -> None:
    at = {"type": "anchor", "anchor": "Firma:", "width": 60}
    stamped = client.post(
        "/doc/stamp",
        json={"path": str(vault / "labelled.pdf"), "image": str(vault / "ink.png"), "at": at},
        headers=ana_key,
    )
    signed = client.post(
        "/doc/signature",
        json={"path": str(vault / "labelled.pdf"), "photo": str(vault / "firma.jpg"), "at": at},
        headers=ana_key,
    )
    refused = client.post("/doc/stamp", json={"path": str(vault / "labelled.pdf"), "at": at}, headers=ana_key)
    assert (stamped.status_code, signed.status_code, refused.status_code) == (200, 200, 400)
    assert placements(await anyio.Path(stamped.json()["path"]).read_bytes()) == [
        pytest.approx((60.0, 0.0, 0.0, 30.0, 100.0, 699.0), abs=3)
    ]
    assert len(placements(await anyio.Path(signed.json()["path"]).read_bytes())) == 1
