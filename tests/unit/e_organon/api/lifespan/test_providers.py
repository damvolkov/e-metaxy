"""tests/unit/e_organon/api/lifespan/providers: every provider opened on one stack, in field order, by its role."""

from dataclasses import fields
from typing import TYPE_CHECKING, ClassVar, Final

import pytest
from litestar.testing import TestClient

import e_organon.api.lifespan.providers as providers_lifespan
import e_organon.providers.adapters.pages.liteparse as liteparse_module
from e_organon.api.lifespan.providers import OPTIONAL, ProvidersState
from e_organon.infra.errors import StoreError
from e_organon.infra.settings import settings as st
from e_organon.main import create_app
from e_organon.ports.auth import AuthPort
from e_organon.ports.coder import CoderPort
from e_organon.ports.database import DatabasePort
from e_organon.ports.http import HTTPPort
from e_organon.ports.provider import Provider
from e_organon.ports.store import StorePort

if TYPE_CHECKING:
    from pathlib import Path

### the roles are the section's fields: a provider the export drops leaves this list with it.
### an optional role is empty here (no DOCLING_URL in tests): the roles are the section's other fields.
ROLES: Final[tuple[str, ...]] = tuple(each.name for each in fields(ProvidersState) if each.name not in OPTIONAL)


async def test_providers_named_in_field_order(client: TestClient) -> None:
    """Each role maps to the provider it holds, every one satisfying the lifecycle contract."""
    roles = client.app.state.system.providers.named
    assert tuple(roles) == ROLES
    assert all(isinstance(provider, Provider) for provider in roles.values())


async def test_providers_open_inside_the_cycle(client: TestClient) -> None:
    """The open sqlite file answers its health while the app runs."""
    assert await client.app.state.system.providers.named["store"].health()


async def test_providers_section_is_typed_and_ported(client: TestClient) -> None:
    section = client.app.state.system.providers
    assert isinstance(section, ProvidersState)
    assert isinstance(section.store, StorePort)
    assert isinstance(section.redis, StorePort)
    assert isinstance(section.http, HTTPPort)
    assert isinstance(section.database, DatabasePort)
    assert isinstance(section.auth, AuthPort)
    assert isinstance(section.coder, CoderPort)
    assert section.store.spec.name == "sqlite"
    assert section.redis.spec.name == "redis"
    assert section.http.spec.name == "wreq"
    assert section.database.spec.name == "psqlpy"


async def test_providers_close_when_the_lifespan_exits() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.system.providers.store
        assert client.get("/health").status_code == 200
        ### alive inside the cycle
        await store.get("anything")
    with pytest.raises(StoreError, match="not open"):
        ### the stack closed it on shutdown
        await store.get("anything")


class FakeLiteParse:
    """liteparse as the adapter opens it: what it was built with, and every read it was asked for."""

    built: ClassVar[list[dict[str, object]]] = []
    reads: ClassVar[list[bytes]] = []

    def __init__(self, **kwargs: object) -> None:
        FakeLiteParse.built.append(kwargs)

    def parse(self, data: bytes) -> None:
        FakeLiteParse.reads.append(data)


def test_providers_doc_ocr_models_live_and_warm_in_its_data_subtree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """OCR on: tessdata is `<ORGANON_DATA>/doc/models/tessdata`, and one blank page is read at open to fetch it."""
    pages = st.providers.adapters.pages.liteparse.model_copy(update={"ocr": True, "tessdata": None})
    on = st.model_copy(
        update={
            "services": st.services.model_copy(update={"ORGANON_DATA": tmp_path}),
            "providers": st.providers.model_copy(
                update={"adapters": st.providers.adapters.model_copy(
                    update={"pages": st.providers.adapters.pages.model_copy(update={"liteparse": pages})}
                )}
            ),
        }
    )  # fmt: skip
    monkeypatch.setattr(providers_lifespan, "st", on)
    monkeypatch.setattr(liteparse_module, "LiteParse", FakeLiteParse)
    FakeLiteParse.built.clear()
    FakeLiteParse.reads.clear()
    with TestClient(create_app()):
        pass
    assert [kwargs["tessdata_path"] for kwargs in FakeLiteParse.built] == [
        str(tmp_path / "doc" / "models" / "tessdata")
    ]
    assert [data[:8] for data in FakeLiteParse.reads] == [b"\x89PNG\r\n\x1a\n"]
