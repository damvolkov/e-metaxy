"""tests/unit/e_metaxy/api/router/converters: the REST door on the live app — render, read, and the 400 refusals.

The real engines answer (the anytomd wheel; docling falls back to the engine's own PDF reading when
docling-serve is out of reach), so `/ops/md` renders the genuine 10-K, `/ops/doc` reads it, and a file the
processor refuses answers 400 with its reason — exactly what a client posts in the deployed app."""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx2

PDF = Path(__file__).resolve().parents[4] / "resources" / "documents" / "filing.pdf"

type Bearer = Callable[[str], dict[str, str]]


def upload(name: str, raw: bytes) -> dict[str, tuple[str, bytes]]:
    return {"file": (name, raw)}


async def test_converters_md_renders_a_real_pdf(http: httpx2.AsyncClient, bearer: Bearer) -> None:
    response = await http.post("/ops/md", files=upload("filing.pdf", PDF.read_bytes()), headers=bearer("work"))
    assert response.status_code == 200
    entry = response.json()["files"][0]
    assert entry["source"] == "pdf"
    assert "10-K" in entry["markdown"]


async def test_converters_doc_reads_a_real_pdf(http: httpx2.AsyncClient, bearer: Bearer) -> None:
    response = await http.post("/ops/doc", files=upload("filing.pdf", PDF.read_bytes()), headers=bearer("work"))
    summary = response.json()
    assert summary["pages"] >= 1
    assert "10-K" in summary["markdown"]


async def test_converters_unsupported_upload_is_a_400(http: httpx2.AsyncClient, bearer: Bearer) -> None:
    response = await http.post("/ops/md", files=upload("mystery", b"\xff\xfe\x00\x01blob"), headers=bearer("work"))
    assert response.status_code == 400
    assert "not a format" in response.json()["error"]


async def test_converters_need_a_token(http: httpx2.AsyncClient) -> None:
    assert (await http.post("/ops/md", files=upload("a.html", b"<h1>Hi</h1>"))).status_code == 401
