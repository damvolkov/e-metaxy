"""tests/conftest: the environment every tier runs in, seeded before `infra.settings` is ever imported.

`settings = Settings()` reads the environment when `infra.settings` is first imported, and pytest imports this module
before any test module or lower conftest — so the seed runs here, at import, and this module imports nothing of the
app. External env wins; a process that inherited another's seed (an xdist worker) takes a private DB_PATH of its own.
The tekton book the tests run on: every profile's roots are /tmp, which is also the workspace."""

import os
import tempfile
from pathlib import Path
from typing import Final

RESOURCES: Final[Path] = Path(__file__).resolve().parent / "resources"
### who seeded this environment: a worker that inherited its controller's seed re-seeds the per-process values.
SEEDER: Final[str] = "E_TESTS_SEEDER"


def seed() -> None:
    """The secrets, the tekton book and a private DB_PATH, unless the environment already names them."""
    own = str(os.getpid())
    inherited = os.environ.get(SEEDER, own) != own
    os.environ.setdefault("CRYPTO__SECRET", "unit-test-secret-0123456789")
    os.environ.setdefault("AUTH_SECRET", "unit-test-auth-secret-0123456789")
    os.environ.setdefault("TEKTON_PROFILES", str(RESOURCES / "profiles" / "book.yaml"))
    os.environ.setdefault("TEKTON_WORKSPACES", "/tmp")
    fresh = inherited or "DB_PATH" not in os.environ
    os.environ["DB_PATH"] = (
        str(Path(tempfile.mkdtemp(prefix="e-organon-tests-")) / "test.db") if fresh else os.environ["DB_PATH"]
    )
    os.environ[SEEDER] = own


seed()
