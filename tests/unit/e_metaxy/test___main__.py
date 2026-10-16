import asyncio

import pytest

from e_metaxy import __main__ as cli
from e_metaxy.core.crypto import Crypto
from e_metaxy.core.settings.base import Secret
from e_metaxy.core.settings.crypto import CryptoSettings


def test_main_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(cli, "serve", lambda: called.append("serve"))
    monkeypatch.setattr(cli, "COMMANDS", {"keys": lambda: called.append("keys")})
    cli.main([])
    cli.main(["keys"])
    assert called == ["serve", "keys"]
    with pytest.raises(SystemExit, match="usage"):
        cli.main(["nope"])


def test_main_serve_hands_the_factory_to_granian(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    class Server:
        def __init__(self, target: str, **options: object) -> None:
            seen.update(options, target=target)

        def serve(self) -> None:
            seen["served"] = True

    monkeypatch.setattr(cli, "Server", Server)
    cli.main(["serve"])
    assert (seen["target"], seen["factory"], seen["served"]) == ("e_metaxy.main:assemble", True, True)


def test_main_keys_prints_a_quoted_secret(capsys: pytest.CaptureFixture[str]) -> None:
    cli.keys()
    line = capsys.readouterr().out.strip()
    assert line.startswith("CRYPTO__SECRET='")
    assert len(line) > len("CRYPTO__SECRET=''") + 32


def test_main_owner_prints_a_hash_that_verifies(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "sesame")
    cli.owner()
    hashed = capsys.readouterr().out.strip().removeprefix("METAXY_AUTH_OWNER_HASH='").removesuffix("'")
    assert asyncio.run(Crypto(CryptoSettings(secret=Secret("k" * 48))).verify_password("sesame", hashed))


@pytest.mark.parametrize(("answers", "message"), [(["", ""], "empty"), (["a", "b"], "differ")], ids=["empty", "differ"])
def test_main_owner_refuses(monkeypatch: pytest.MonkeyPatch, answers: list[str], message: str) -> None:
    replies = iter(answers)
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(replies))
    with pytest.raises(SystemExit, match=message):
        cli.owner()
