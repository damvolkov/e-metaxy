"""tests/unit/e_organon/api/router/doc: one route, two readings — JSON in batch, server-sent events when asked for."""

from typing import TYPE_CHECKING

import anyio
import pytest

from support.pdf import placements
from support.redact import pdfium_text
from support.signed import validated

if TYPE_CHECKING:
    from pathlib import Path

    from litestar.testing import TestClient

    from support.pki import Pki

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


def test_doc_ocr_is_no_route_until_the_engine_is_on(vault: Path, client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/doc/ocr", json={"path": str(vault / "ink.png")}, headers=ana_key)
    assert response.status_code == 404


def test_doc_ocr_answers_the_words_with_their_boxes(
    vault: Path, ocr_on: Path, client: TestClient, ana_key: dict[str, str]
) -> None:
    response = client.post("/doc/ocr", json={"path": str(vault / "ink.png")}, headers=ana_key)
    page = response.json()["pages"][0]
    assert (response.status_code, page["text"], page["words"][0]["box"]) == (200, "hola", [10, 40, 110, 80])


def test_doc_ocr_queues_as_a_job_when_asked(
    vault: Path, ocr_on: Path, client: TestClient, ana_key: dict[str, str]
) -> None:
    response = client.post(
        "/organon/submit", json={"tool": "doc/ocr", "input": {"path": str(vault / "ink.png")}}, headers=ana_key
    )
    job = client.get(f"/jobs/{response.json()['job']}", headers=ana_key)
    assert (response.status_code, job.json()["kind"]) == (202, "doc/ocr")


def test_doc_sign_is_no_route_until_a_key_is_set(vault: Path, client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/doc/sign", json={"path": str(vault / "labelled.pdf")}, headers=ana_key)
    assert response.status_code == 404


async def test_doc_sign_answers_a_pdf_that_validates(
    vault: Path, sign_on: Pki, client: TestClient, ana_key: dict[str, str]
) -> None:
    response = client.post("/doc/sign", json={"path": str(vault / "labelled.pdf")}, headers=ana_key)
    _, status = await validated(await anyio.Path(response.json()["path"]).read_bytes(), sign_on)
    assert (response.status_code, status.bottom_line) == (200, True)


def test_doc_sign_a_visible_signature_without_an_appearance_is_422(
    vault: Path, sign_on: Pki, client: TestClient, ana_key: dict[str, str]
) -> None:
    order = {"path": str(vault / "labelled.pdf"), "at": {"type": "box", "page": 0, "x": 1, "y": 1, "width": 5}}
    assert client.post("/doc/sign", json=order, headers=ana_key).status_code == 400


async def test_doc_compose_over_rest_and_queued_as_a_job(
    vault: Path, client: TestClient, ana_key: dict[str, str], invoice_data: dict
) -> None:
    order = {"template": "invoice", "data": invoice_data}
    batch = client.post("/doc/compose", json=order, headers=ana_key)
    queued = client.post("/organon/submit", json={"tool": "doc/compose", "input": order}, headers=ana_key)
    done = client.get(f"/jobs/{queued.json()['job']}/events", headers=ana_key)
    pdf = await anyio.Path(batch.json()["path"]).read_bytes()
    assert (batch.status_code, pdf[:5], queued.status_code, done.text.count("event: done")) == (200, b"%PDF-", 202, 1)


async def test_doc_redact_over_rest_and_queued_as_a_job(
    vault: Path, client: TestClient, ana_key: dict[str, str]
) -> None:
    order = {"path": str(vault / "labelled.pdf"), "terms": ["otra"]}
    batch = client.post("/doc/redact", json=order, headers=ana_key)
    queued = client.post("/organon/submit", json={"tool": "doc/redact", "input": order}, headers=ana_key)
    done = client.get(f"/jobs/{queued.json()['job']}/events", headers=ana_key)
    after = await anyio.Path(batch.json()["path"]).read_bytes()
    assert (batch.status_code, batch.json()["count"], "otra" in pdfium_text(after), "Firma:" in pdfium_text(after)) == (
        200,
        1,
        False,
        True,
    )
    assert (queued.status_code, done.text.count("event: done")) == (202, 1)


def test_doc_redact_with_nothing_to_strike_is_refused(vault: Path, client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/doc/redact", json={"path": str(vault / "labelled.pdf")}, headers=ana_key)
    assert response.status_code == 400
