"""Install or update the lgess_live service on the ESS over SSH.

Mirrors install.sh: copies the bundled service and init script, links the
init script into runlevel 5 and restarts the service. Only files below
/usr/local/lgess_live, /etc/init.d/lgess_live and /etc/rc5.d/S95lgess_live are
written; LG's own software is not touched.
"""
from __future__ import annotations

from pathlib import Path

import asyncssh

ESS_DIR = Path(__file__).parent / "ess"
REMOTE_DIR = "/usr/local/lgess_live"
REMOTE_INIT = "/etc/init.d/lgess_live"
REMOTE_LINK = "/etc/rc5.d/S95lgess_live"


class DeployError(Exception):
    """Installing the service failed."""


def _bundled() -> tuple[bytes, bytes]:
    return (ESS_DIR / "lgess_live.py").read_bytes(), (ESS_DIR / "lgess_live.init").read_bytes()


async def deploy(host: str, username: str, password: str | None = None, port: int = 22) -> str:
    """Install/update the service; returns the output of the restart."""
    service, init = _bundled()
    try:
        # The ESS's host key is not known in advance and the device sits in the
        # local network; the key is accepted on first use (as `ssh` would ask).
        async with asyncssh.connect(
            host, port=port, username=username, password=password or None,
            known_hosts=None, client_keys=None, connect_timeout=15,
        ) as conn:
            await conn.run(f"mkdir -p {REMOTE_DIR}", check=True)
            await conn.run(f"cat > {REMOTE_DIR}/lgess_live.py", input=service.decode(), check=True)
            await conn.run(f"cat > {REMOTE_INIT} && chmod 755 {REMOTE_INIT}", input=init.decode(), check=True)
            res = await conn.run(
                f"ln -sf ../init.d/lgess_live {REMOTE_LINK} && {REMOTE_INIT} restart", check=True)
            return (res.stdout or "").strip()
    except (OSError, asyncssh.Error) as err:
        raise DeployError(f"{type(err).__name__}: {err}".rstrip(": ")) from err
