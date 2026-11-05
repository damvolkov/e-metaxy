"""tests/unit/e_organon/services/doc/compose: doc/compose over the real typst adapter — a template by name (the deployment's
folder first, then the shipped ones) or by path under the roots becomes a PDF/A in the outbox, the same file for the same
input; the shipped invoice is held to a golden text; what cannot be found or read fails the run."""

import io
from typing import TYPE_CHECKING, Any

import anyio
import pikepdf
import pypdfium2 as pdfium
import pytest

from e_organon.models.doc import ComposeIn
from e_organon.models.flow import Done, Failed, Step

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_resources import Resources

    from e_organon.services.doc.compose import ComposeDocService


async def pdf_of(composer: ComposeDocService, order: ComposeIn) -> bytes:
    out = await composer.run(order)
    return await anyio.Path(out.path).read_bytes()


def text_of(pdf: bytes) -> list[str]:
    document = pdfium.PdfDocument(pdf)
    return [document[index].get_textpage().get_text_range() for index in range(len(document))]


async def test_compose_steps_then_the_pdf(composer: ComposeDocService) -> None:
    events = [event async for event in composer.events(ComposeIn(template="hello", data={"name": "Ana"}))]
    assert [event.name for event in events if isinstance(event, Step)] == ["resolve", "compose", "keep"]
    assert isinstance(events[-1], Done)


async def test_compose_a_named_template_over_its_data(composer: ComposeDocService) -> None:
    pdf = await pdf_of(composer, ComposeIn(template="hello", data={"name": "Ñandú"}))
    assert text_of(pdf)[0].strip() == "Hola, Ñandú"


async def test_compose_a_template_by_path_reads_beside_itself(composer: ComposeDocService, templates: Path) -> None:
    pdf = await pdf_of(composer, ComposeIn(template=str(templates / "reads.typ")))
    assert text_of(pdf)[0].strip() == "desde el disco"


async def test_compose_the_deployments_template_hides_the_shipped_one(
    composer: ComposeDocService, templates: Path
) -> None:
    (templates / "invoice.typ").write_bytes(b"Mi factura")
    assert text_of(await pdf_of(composer, ComposeIn(template="invoice")))[0].strip() == "Mi factura"


async def test_compose_the_same_input_is_the_same_file(composer: ComposeDocService) -> None:
    order = ComposeIn(template="hello", data={"name": "Ana"})
    assert (await composer.run(order)).path == (await composer.run(order)).path


async def test_compose_the_shipped_invoice_is_the_golden_text(
    composer: ComposeDocService, invoice_data: dict[str, Any], resources: Resources
) -> None:
    pdf = await pdf_of(composer, ComposeIn(template="invoice", data=invoice_data))
    golden = (resources.path / "golden" / "invoice.txt").read_bytes().decode()
    with pikepdf.open(io.BytesIO(pdf)) as opened:
        pdfa = str(opened.open_metadata()["pdfaid:part"])
    assert ("\f".join(text_of(pdf)), len(text_of(pdf)), pdfa) == (golden, 2, "2")


@pytest.mark.parametrize(
    ("template", "kind"),
    [("nope", "TemplateNotFoundError"), ("/etc/hostname", "OutsideRootsError"), ("../x", "OutsideRootsError")],
    ids=["unknown-name", "outside-roots", "traversal-is-a-path"],
)
async def test_compose_what_cannot_be_found_fails_the_run(
    composer: ComposeDocService, template: str, kind: str
) -> None:
    events = [event async for event in composer.events(ComposeIn(template=template))]
    assert isinstance(events[-1], Failed)
    assert events[-1].kind == kind


async def test_compose_a_template_that_does_not_compile_fails_the_run(
    composer: ComposeDocService, templates: Path
) -> None:
    (templates / "broken.typ").write_bytes(b"#nope")
    events = [event async for event in composer.events(ComposeIn(template="broken"))]
    assert isinstance(events[-1], Failed)
    assert (events[-1].kind, "unknown variable" in events[-1].reason) == ("ParseError", True)
