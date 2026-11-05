"""tests/benchmark/conftest: the services behind the live app, faked (`support.app`), as every tier runs them."""

from support.app import coder, keys, psqlpy, queue

__all__ = ["coder", "keys", "psqlpy", "queue"]
