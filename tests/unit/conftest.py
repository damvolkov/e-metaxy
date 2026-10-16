"""Unit-wide fixtures: the resource tree, the profile book and a real sqlite ledger on a temp file."""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from e_metaxy.adapters.sqlite import SQLiteAdapter
from e_metaxy.core.settings.db import DbSettings
from e_metaxy.models.profile import Profile

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


@pytest.fixture
def resources() -> Path:
    return RESOURCES


@pytest.fixture
def book(resources: Path) -> Mapping[str, Profile]:
    return Profile.book((resources / "profiles" / "book.yaml").read_bytes())


@pytest.fixture
async def ledger(tmp_path: Path) -> AsyncIterator[SQLiteAdapter]:
    async with SQLiteAdapter(DbSettings(db_path=tmp_path / "ledger.db")) as store:
        yield store


@pytest.fixture
def fake_claude(resources: Path, tmp_path: Path) -> str:
    """An executable `claude` whose `mcp serve` is the stand-in server, run by this interpreter."""
    binary = tmp_path / "claude"
    binary.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{resources / "bin" / "claude.py"}" "$@"\n')
    binary.chmod(0o755)
    return str(binary)
