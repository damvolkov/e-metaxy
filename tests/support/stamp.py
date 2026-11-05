"""tests/support/stamp: the shapes of the stamp fixtures — an order run to the PDF it makes, or to the failure it ends in."""

from collections.abc import Awaitable, Callable

from e_organon.models.doc import StampIn
from e_organon.models.flow import Failed

type Stamped = Callable[[StampIn], Awaitable[bytes]]
type Refusal = Callable[[StampIn], Awaitable[Failed]]
