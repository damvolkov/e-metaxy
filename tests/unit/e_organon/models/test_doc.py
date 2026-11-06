"""tests/unit/e_organon/models/doc: what doc/stamp and doc/signature are asked — `at` a tagged union, an image or a text."""

import msgspec
import pytest

from e_organon.models.doc import AtAnchor, AtBox, AtField, RedactIn, SignatureIn, StampIn
from e_organon.ports.redact import RedactBox


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"type": "field", "field": "firma"}, AtField(field="firma")),
        (
            {"type": "anchor", "anchor": "Firma:", "occurrence": 2, "offset": [5, -2], "width": 60},
            AtAnchor(anchor="Firma:", occurrence=2, offset=(5.0, -2.0), width=60.0),
        ),
        ({"type": "box", "page": 1, "x": 10, "y": 20, "width": 30}, AtBox(page=1, x=10.0, y=20.0, width=30.0)),
    ],
    ids=["field", "anchor", "box"],
)
def test_stamp_at_is_a_tagged_union(raw: dict, expected: object) -> None:
    assert msgspec.convert({"path": "a.pdf", "text": "x", "at": raw}, StampIn).at == expected


@pytest.mark.parametrize(
    "raw",
    [
        {"path": "a.pdf", "at": {"type": "field", "field": "f"}},
        {"path": "a.pdf", "image": "a.png", "text": "x", "at": {"type": "field", "field": "f"}},
        {"path": "a.pdf", "text": "x", "at": {"type": "field", "field": "f"}, "opacity": 2},
        {"path": "a.pdf", "text": "x", "at": {"type": "anchor", "anchor": "a", "occurrence": 0}},
        {"path": "a.pdf", "text": "x", "at": {"type": "nowhere"}},
    ],
    ids=["neither", "both", "opacity", "occurrence", "kind"],
)
def test_stamp_refuses_what_is_not_a_stamp(raw: dict) -> None:
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert(raw, StampIn)


def test_signature_takes_a_photo_and_a_place() -> None:
    order = msgspec.convert({"path": "a.pdf", "photo": "p.jpg", "at": {"type": "field", "field": "firma"}}, SignatureIn)
    assert (order.color, order.at) == (True, AtField(field="firma"))


def test_redact_takes_terms_or_boxes() -> None:
    box = {"page": 0, "x": 1, "y": 2, "width": 3, "height": 4}
    order = msgspec.convert({"path": "a.pdf", "terms": ["x"], "boxes": [box]}, RedactIn)
    assert (order.regex, order.pages, order.boxes) == (
        False,
        [],
        [RedactBox(page=0, x=1.0, y=2.0, width=3.0, height=4.0)],
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"path": "a.pdf"},
        {"path": "a.pdf", "terms": [""]},
        {"path": "a.pdf", "boxes": [{"page": 0, "x": 1, "y": 2, "width": 0, "height": 4}]},
        {"path": "a.pdf", "terms": ["x"], "pages": [-1]},
    ],
    ids=["nothing", "empty-term", "flat-box", "page"],
)
def test_redact_refuses_what_strikes_nothing(raw: dict) -> None:
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert(raw, RedactIn)
