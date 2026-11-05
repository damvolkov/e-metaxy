"""tests/unit/e_organon: the live app on the real graph, a request away — `client` over the faked services of `tests/conftest`
(`keys`: `ana` an account, `root` the admin; `ana_key` and `root_key` the `Authorization` headers that carry theirs), and what
the access log wrote, recorded; and what every tekton test runs on: `book`, the profile book; `ledger`, a real sqlite file
on a temporary path; `bridge`, the engine over `coder` (the scripted one of `tests/conftest`), `wire` the builder of more,
`settle` the wait that ends a task."""

from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient
from pydantic import SecretStr

from e_organon import main as main_module
from e_organon.api import middlewares as middlewares_module
from e_organon.api.lifespan import engines as engines_module
from e_organon.api.lifespan import mcp as mcp_lifespan_module
from e_organon.api.lifespan import providers as providers_module
from e_organon.api.lifespan import services as services_module
from e_organon.engines.bridge import BridgeEngine, Task, TaskOrder
from e_organon.infra.settings import settings as st
from e_organon.main import create_app
from e_organon.ops.projects import NamedProjects
from e_organon.ports.coder import Profile
from e_organon.ports.ocr import OcrWord
from e_organon.providers.drivers.store.sqlite import SqliteDriver
from support import pki as pki_module
from support.ink import ink_png
from support.ocr import FakeOcr
from support.pdf import labelled
from support.photo import photo

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Mapping

    from pytest_resources import Resources

    from support.bridge import Settle, Wire
    from support.coder import ScriptedCoder
    from support.pki import Pki


class RequestLogs:
    """The `request` events the access log writes, fields only — what a test asserts a request was logged with."""

    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def info(self, event: str, **fields: object) -> None:
        _ = event == "request" and self.requests.append(fields)


@pytest.fixture
def request_logs(monkeypatch: pytest.MonkeyPatch) -> RequestLogs:
    """The access log's logger replaced by a recorder for the test's length."""
    recorder = RequestLogs()
    monkeypatch.setattr(middlewares_module, "logger", recorder)
    return recorder


@pytest.fixture
def ana_key() -> dict[str, str]:
    return {"Authorization": "Bearer t-ana"}


@pytest.fixture
def root_key() -> dict[str, str]:
    return {"Authorization": "Bearer t-root"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A vault of the test's own as the tools' only root, its outbox inside, a `plan.md` in it — request it before `client`, which starts
    the app on the roots the settings say then."""
    (tmp_path / "plan.md").write_text("# Plan\n\nStep one.\n")
    (tmp_path / "firma.jpg").write_bytes(photo()[0])
    (tmp_path / "labelled.pdf").write_bytes(labelled())
    (tmp_path / "ink.png").write_bytes(ink_png())
    ### the outbox inside the root, as in the house: an output is the next tool's input — and never lands in the real vault.
    on = st.model_copy(update={"ORGANON_ROOTS": (tmp_path,), "ORGANON_OUTBOX": tmp_path / "outbox"})
    monkeypatch.setattr(services_module, "st", on)
    monkeypatch.setattr(engines_module, "st", on)
    return tmp_path


@pytest.fixture
def fake_ocr() -> FakeOcr:
    """The engine `ocr_on` opens in place of RapidOCR: it reads every image as one word."""
    return FakeOcr((OcrWord(text="hola", box=(10, 20, 110, 60)),))


@pytest.fixture
def ocr_on(monkeypatch: pytest.MonkeyPatch, fake_ocr: FakeOcr, tmp_path: Path) -> Path:
    """The app with OCR_ENABLED: its engine is the fake, built where the real one would keep its models — the returned
    `<ORGANON_DATA>/doc/models/rapidocr`. Request it before `client`."""
    on = st.model_copy(update={"OCR_ENABLED": True, "ORGANON_DATA": tmp_path / "data"})
    monkeypatch.setattr(main_module, "st", on)
    monkeypatch.setattr(providers_module, "st", on)
    monkeypatch.setattr(mcp_lifespan_module, "st", on)
    monkeypatch.setattr(providers_module, "RapidocrAdapter", lambda *, models: fake_ocr.keeping(models))
    return tmp_path / "data" / "doc" / "models" / "rapidocr"


@pytest.fixture(scope="session")
def pki(tmp_path_factory: pytest.TempPathFactory) -> Pki:
    """A throwaway CA and signer, made once for the run."""
    return pki_module.make(tmp_path_factory.mktemp("pki"))


@pytest.fixture
def sign_on(monkeypatch: pytest.MonkeyPatch, pki: Pki) -> Pki:
    """The app with SIGN_P12 set to the throwaway signer's PKCS#12 — `doc/sign` is a route and a tool. Request it before
    `client`."""
    on = st.model_copy(update={"SIGN_P12": pki.p12, "SIGN_P12_PASSWORD": SecretStr(pki.password)})
    monkeypatch.setattr(main_module, "st", on)
    monkeypatch.setattr(providers_module, "st", on)
    monkeypatch.setattr(mcp_lifespan_module, "st", on)
    return pki


@pytest.fixture
def book(resources: Resources) -> Mapping[str, Profile]:
    """The tests' profile book: `research`, `code`, `direct`, each admitting `/tmp` alone."""
    return Profile.book((resources.path / "profiles" / "book.yaml").read_bytes())


@pytest.fixture
async def ledger(tmp_path: Path) -> AsyncIterator[SqliteDriver]:
    async with SqliteDriver(path=tmp_path / "ledger.db", timeout=timedelta(seconds=5)) as store:
        yield store


@pytest.fixture
def order() -> TaskOrder:
    return TaskOrder(prompt="ping", profile="research", cwd="/tmp")


@pytest.fixture
def wire(ledger: SqliteDriver, book: Mapping[str, Profile]) -> Wire:
    def build(coder: ScriptedCoder, limit: int = 2) -> BridgeEngine:
        return BridgeEngine(
            coders={coder.kind: coder}, ledger=ledger, profiles=book, projects=NamedProjects(Path("/tmp")), limit=limit
        )

    return build


@pytest.fixture
async def bridge(wire: Wire, coder: ScriptedCoder) -> AsyncIterator[BridgeEngine]:
    async with wire(coder) as opened:
        yield opened


@pytest.fixture
def settle() -> Settle:
    async def wait(bridge: BridgeEngine, task: Task) -> Task:
        return await bridge.status(task.id, wait=2.0)

    return wait
