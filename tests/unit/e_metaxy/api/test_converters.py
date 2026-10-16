"""tests/unit/e_metaxy/api/converters: the REST surface via an ASGI `TestClient` — render, read, and the 400 refusals.

Real ports are connected around each request (the engine is the anytomd wheel), so `/md` renders the genuine
10-K, `/doc` reads it, and a file the processor refuses answers 400 with its reason — exactly what a client
posts to `/ops/md` and `/ops/doc` in the deployed app."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx2

from e_metaxy.adapters.docling import DoclingAdapter
from e_metaxy.api.converters import create_app
from e_metaxy.core.settings.md import MDSettings
from e_metaxy.logic.converters import Converters
from e_metaxy.processors.doc import DocProcessor
from e_metaxy.processors.md import MDProcessor

PDF = Path(__file__).resolve().parents[3] / "resources" / "documents" / "filing.pdf"
AnytomdAdapter = __import__("e_metaxy.adapters.md.anytomd", fromlist=["AnytomdAdapter"]).AnytomdAdapter


@asynccontextmanager
async def client(**conf: Any):
    anatomd, docling = AnytomdAdapter(MDSettings(**conf)), DoclingAdapter()
    app = create_app(Converters(MDProcessor(anatomd, MDSettings(**conf)), DocProcessor(docling)))
    async with anatomd, docling, httpx2.AsyncClient(transport=httpx2.ASGITransport(app), base_url="http://ops") as http:
        yield http


def upload(name: str, raw: bytes) -> dict[str, tuple[str, bytes]]:
    return {"file": (name, raw)}


async def test_health_is_wired() -> None:
    async with client() as http:
        assert (await http.get("/health")).json() == {"status": "ok"}


async def test_md_renders_a_real_pdf() -> None:
    async with client() as http:
        response = await http.post("/md", files=upload("filing.pdf", PDF.read_bytes()))
    assert response.status_code == 200
    entry = response.json()["files"][0]
    assert entry["source"] == "pdf"
    assert "10-K" in entry["markdown"]


async def test_doc_reads_a_real_pdf() -> None:
    async with client() as http:
        summary = (await http.post("/doc", files=upload("filing.pdf", PDF.read_bytes()))).json()
    assert summary["pages"] >= 1
    assert "10-K" in summary["markdown"]


async def test_an_unsupported_upload_is_a_400() -> None:
    async with client() as http:
        response = await http.post("/md", files=upload("mystery", b"\xff\xfe\x00\x01blob"))
    assert response.status_code == 400
    assert "not a format" in response.json()["error"]


async def test_an_oversized_upload_is_a_400() -> None:
    async with client(md_max_input_bytes=4) as http:
        response = await http.post("/md", files=upload("filing.pdf", PDF.read_bytes()))
    assert response.status_code == 400
    assert "MD_MAX_INPUT_BYTES" in response.json()["error"]
