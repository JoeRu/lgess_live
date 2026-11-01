"""Integrates power (W) into energy (kWh) for the energy dashboard."""
from __future__ import annotations

from .const import MAX_INTEGRATION_GAP


class EnergyIntegrator:
    """Left Riemann sum of a non-negative power value, in kWh.

    Gaps longer than MAX_INTEGRATION_GAP are not integrated: after an outage
    the counter continues from where it stopped instead of guessing.
    """

    def __init__(self, total_kwh: float = 0.0) -> None:
        self.total_kwh = total_kwh
        self._last_ts: float | None = None
        self._last_w: float | None = None

    def add(self, power_w: float, ts: float) -> float:
        power_w = max(float(power_w), 0.0)
        if self._last_ts is not None and self._last_w is not None:
            dt = ts - self._last_ts
            if 0 < dt <= MAX_INTEGRATION_GAP:
                self.total_kwh += self._last_w * dt / 3_600_000
        if self._last_ts is None or ts > self._last_ts:
            self._last_ts, self._last_w = ts, power_w
        return self.total_kwh
