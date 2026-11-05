"""tests/unit/e_organon/api/router: what a route's server-sent body is read with — `told`, a body as its (event, data) pairs."""

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from support.sse import Told


@pytest.fixture
def told() -> Told:
    """A server-sent body as its (event, data) pairs, the keep-alive comments left out."""

    def read(body: str) -> list[tuple[str, dict]]:
        blocks = [block for block in body.replace("\r\n", "\n").split("\n\n") if "event:" in block]
        return [
            (
                next(line.removeprefix("event: ") for line in block.splitlines() if line.startswith("event: ")),
                json.loads(
                    next(line.removeprefix("data: ") for line in block.splitlines() if line.startswith("data: "))
                ),
            )
            for block in blocks
        ]

    return read
