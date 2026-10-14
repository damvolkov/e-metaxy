from pathlib import Path
from typing import TYPE_CHECKING

import msgspec
import pytest

from e_metaxy.models.profile import CoderKind, Profile, ProfileMode

if TYPE_CHECKING:
    from collections.abc import Mapping


async def test_profile_book(book: Mapping[str, Profile]) -> None:
    assert {name: (p.name, p.coder, p.mode) for name, p in book.items()} == {
        "research": ("research", CoderKind.CLAUDE, ProfileMode.DONT_ASK),
        "code": ("code", CoderKind.CLAUDE, ProfileMode.ACCEPT_EDITS),
    }


async def test_profile_book_bypass_refused(resources: Path) -> None:
    with pytest.raises(msgspec.ValidationError, match="mode"):
        Profile.book((resources / "profiles" / "bypass.yaml").read_bytes())


@pytest.mark.parametrize(
    ("cwd", "expected"),
    [("/tmp", True), ("/tmp/deep/er", True), ("/etc", False), ("/tmpfoo", False)],
    ids=["root", "below", "outside", "prefix"],
)
async def test_profile_admits(book: Mapping[str, Profile], cwd: str, expected: bool) -> None:
    assert book["research"].admits(Path(cwd)) is expected


async def test_profile_admits_without_roots() -> None:
    assert Profile(name="bare").admits(Path("/tmp")) is False
