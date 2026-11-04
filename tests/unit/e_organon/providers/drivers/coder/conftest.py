"""tests/unit/e_organon/providers/drivers/coder: a driver on a CLI that is never run, a spec under the `code` profile, and a
`claude` executable whose `mcp serve` is the stand-in server of `tests/resources/bin/claude.py`."""

import sys
from typing import TYPE_CHECKING

import pytest

from e_organon.ports.coder import CoderSpec
from e_organon.providers.drivers.coder.claude import ClaudeDriver

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from pytest_resources import Resources

    from e_organon.ports.coder import Profile


@pytest.fixture
def claude() -> ClaudeDriver:
    return ClaudeDriver("/usr/bin/claude")


@pytest.fixture
def spec(book: Mapping[str, Profile]) -> CoderSpec:
    return CoderSpec(prompt="p", cwd="/tmp", profile=book["code"], session="s-1", fork=True)


@pytest.fixture
def fake_claude(resources: Resources, tmp_path: Path) -> str:
    """An executable `claude` whose `mcp serve` is the stand-in server, run by this interpreter."""
    binary = tmp_path / "claude"
    binary.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{resources.path / "bin" / "claude.py"}" "$@"\n')
    binary.chmod(0o755)
    return str(binary)
