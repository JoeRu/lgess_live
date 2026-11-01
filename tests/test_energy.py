from custom_components.lgess_live.energy import EnergyIntegrator


def test_left_riemann_in_kwh():
    e = EnergyIntegrator()
    for t in range(0, 1001, 10):   # 3.6 kW for 1000 s in 10 s steps -> 1 kWh
        e.add(3600, t)
    assert abs(e.total_kwh - 1.0) < 1e-9


def test_gap_is_not_integrated():
    e = EnergyIntegrator(5.0)
    e.add(1000, 0)
    e.add(1000, 3600)     # 1 h gap (outage): nothing invented
    assert e.total_kwh == 5.0
    e.add(1000, 3610)     # normal step afterwards counts again
    assert abs(e.total_kwh - 5.0 - 1000 * 10 / 3_600_000) < 1e-12


def test_negative_power_counts_as_zero_and_time_going_back_is_ignored():
    e = EnergyIntegrator()
    e.add(-500, 0)
    e.add(1000, 10)
    assert e.total_kwh == 0.0
    e.add(1000, 5)        # clock went backwards: no change, no negative step
    assert e.total_kwh == 0.0
