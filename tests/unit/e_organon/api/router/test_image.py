"""tests/unit/e_organon/api/router/image: image/cutout over REST — a key, a PNG in the outbox, streamed, batched or queued."""

import io
from typing import TYPE_CHECKING

import anyio
from PIL import Image

if TYPE_CHECKING:
    from pathlib import Path

    from litestar.testing import TestClient

    from support.sse import Told

SSE = {"accept": "text/event-stream"}
ASYNC = {"prefer": "respond-async"}


def test_cutout_needs_a_key(client: TestClient) -> None:
    assert client.post("/image/cutout", json={"path": "/x"}).status_code == 401


async def test_cutout_batch_answers_the_png(vault: Path, client: TestClient, ana_key: dict[str, str]) -> None:
    response = client.post("/image/cutout", json={"path": str(vault / "firma.jpg")}, headers=ana_key)
    out = response.json()
    image = Image.open(io.BytesIO(await anyio.Path(out["path"]).read_bytes()))
    assert (response.status_code, image.mode, out["size"] > 0) == (200, "RGBA", True)


def test_cutout_streams_its_steps(vault: Path, client: TestClient, ana_key: dict[str, str], told: Told) -> None:
    body = {"path": str(vault / "firma.jpg")}
    with client.stream("POST", "/image/cutout", json=body, headers=ana_key | SSE) as response:
        seen = told("".join(response.iter_text()))
    assert [(name, data.get("name")) for name, data in seen[:-1]] == [
        ("step", "resolve"),
        ("step", "measure"),
        ("step", "cut"),
        ("step", "keep"),
    ]
    assert seen[-1][0] == "done"


def test_cutout_in_the_background_settles_with_the_batch_answer(
    vault: Path, client: TestClient, ana_key: dict[str, str]
) -> None:
    body = {"path": str(vault / "firma.jpg")}
    batch = client.post("/image/cutout", json=body, headers=ana_key).json()
    job = client.post("/image/cutout", json=body, headers=ana_key | ASYNC).json()["job"]
    with client.stream("GET", f"/jobs/{job}/events", headers=ana_key) as response:
        _ = "".join(response.iter_text())
    settled = client.get(f"/jobs/{job}", headers=ana_key).json()
    assert (settled["kind"], settled["state"], settled["progress"]["done"]) == ("image/cutout", "completed", batch)
