"""HTTP client for the lgess_live service running on the ESS."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

REQUIRED_KEY = "grid_power_w"


class LgEssError(Exception):
    """The service could not be reached or returned no valid values."""


class LgEssApi:
    """Fetches /api/live from the service on the ESS."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self._session = session
        self.url = f"http://{host}:{port}/api/live"

    async def fetch(self, timeout: float = 4.0) -> dict[str, Any]:
        try:
            async with asyncio.timeout(timeout):
                async with self._session.get(self.url) as resp:
                    if resp.status != 200:
                        raise LgEssError(f"HTTP {resp.status} from {self.url}")
                    data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise LgEssError(f"{type(err).__name__}: {err}".rstrip(": ")) from err
        if not isinstance(data, dict) or REQUIRED_KEY not in data:
            raise LgEssError(f"unexpected answer from {self.url}")
        return data
