"""tests/unit/e_organon/mcp/tools/doc: the doc tools an agent meets that a deployment turns on or ships with — `doc_sign` where a
key is set, `doc_compose` over the shipped invoice."""

from typing import TYPE_CHECKING, Any

import anyio

from support.mcp import call
from support.signed import validated

if TYPE_CHECKING:
    from pathlib import Path

    from support.mcp import Connect
    from support.pki import Pki


async def test_doc_sign_is_a_tool_only_with_a_key(
    vault: Path, sign_on: Pki, connect: Connect, ana_key: dict[str, str]
) -> None:
    signed = await call(connect, "doc_sign", {"path": str(vault / "labelled.pdf")}, ana_key)
    _, status = await validated(await anyio.Path(signed["path"]).read_bytes(), sign_on)
    assert status.bottom_line


async def test_doc_compose_is_a_tool_that_writes_the_pdf(
    vault: Path, connect: Connect, ana_key: dict[str, str], invoice_data: dict[str, Any]
) -> None:
    composed = await call(connect, "doc_compose", {"template": "invoice", "data": invoice_data}, ana_key)
    assert (await anyio.Path(composed["path"]).read_bytes())[:5] == b"%PDF-"
