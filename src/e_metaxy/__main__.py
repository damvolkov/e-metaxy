"""e_metaxy: `python -m e_metaxy` / `e-metaxy` — serve the bridge with granian (Rust ASGI) on loopback."""

from granian.constants import Interfaces
from granian.server import Server

from core.logger import setup
from core.settings import settings as core
from e_metaxy.config.metaxy import MetaxySettings


def main() -> None:
    st = MetaxySettings()
    setup(env=core.app.app_env)
    Server(
        "e_metaxy.main:assemble",
        address=st.host,
        port=st.port,
        interface=Interfaces.ASGI,
        factory=True,
        workers=1,
        log_access=False,
    ).serve()


if __name__ == "__main__":
    main()
