"""tests/unit/e_organon/ports/coder: the profile book — named after its keys, frozen, every mode a member — and the roots a
profile admits."""

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest

from e_organon.ports.coder import CoderKind, Profile, ProfileMode

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pytest_resources import Resources


async def test_coder_book(book: Mapping[str, Profile]) -> None:
    assert {name: (p.name, p.coder, p.mode) for name, p in book.items()} == {
        "research": ("research", CoderKind.CLAUDE, ProfileMode.DONT_ASK),
        "code": ("code", CoderKind.CLAUDE, ProfileMode.ACCEPT_EDITS),
        "direct": ("direct", CoderKind.CLAUDE, ProfileMode.BYPASS),
    }


async def test_coder_book_bypass_loads(resources: Resources) -> None:
    book = Profile.book((resources.path / "profiles" / "bypass.yaml").read_bytes())
    assert book["reckless"].mode is ProfileMode.BYPASS


async def test_coder_book_of_the_repository_loads() -> None:
    book = Profile.book(await anyio.Path("profiles.yaml").read_bytes())
    assert {"direct", "research", "plan", "code"} <= set(book)


@pytest.mark.parametrize(
    ("cwd", "expected"),
    [("/tmp", True), ("/tmp/deep/er", True), ("/etc", False), ("/tmpfoo", False)],
    ids=["root", "below", "outside", "prefix"],
)
async def test_coder_profile_admits(book: Mapping[str, Profile], cwd: str, expected: bool) -> None:
    assert book["research"].admits(Path(cwd)) is expected


async def test_coder_profile_admits_without_roots() -> None:
    assert Profile(name="bare").admits(Path("/tmp")) is False
