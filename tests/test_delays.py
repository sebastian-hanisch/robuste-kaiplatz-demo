import dataclasses
import random
import statistics

import pytest

import rb_constants as C
from rb_delays import actual_arrivals, actual_instance, buffered_instance, draw_delays, scenario_delays
from rb_scenario import make_instance


def _inst(n=9, seed=7):
    return make_instance(n_ships=n, seed=seed)


def test_same_seed_same_draw():
    inst = _inst()
    for kind in C.DELAY_KINDS:
        assert scenario_delays(inst, 8, kind, 5) == scenario_delays(inst, 8, kind, 5)


def test_different_seed_different_draw():
    inst = _inst(n=20)
    for kind in C.DELAY_KINDS:
        assert scenario_delays(inst, 8, kind, 1) != scenario_delays(inst, 8, kind, 2)


def test_delays_do_not_depend_on_the_fleet_seed():
    # eigener Strom: Flotte neu würfeln ändert die Verspätungen bei gleicher Schiffszahl nicht (und umgekehrt die Flotte nicht durch den Verspätungs-Seed)
    a, b = _inst(seed=1), _inst(seed=2)
    assert a.ships != b.ships
    for kind in C.DELAY_KINDS:
        assert scenario_delays(a, 8, kind, 5) == scenario_delays(b, 8, kind, 5)
    before = _inst(seed=1)
    scenario_delays(before, 8, "exp", 99)
    assert before == _inst(seed=1)


@pytest.mark.parametrize("kind", C.DELAY_KINDS)
def test_delays_are_non_negative_integers_for_every_ship(kind):
    inst = _inst(n=12)
    d = scenario_delays(inst, 6, kind, 3)
    assert set(d) == {s.index for s in inst.ships}
    assert all(isinstance(v, int) and v >= 0 for v in d.values())


@pytest.mark.parametrize("kind", C.DELAY_KINDS)
def test_zero_mean_means_everyone_on_time_and_consumes_no_randomness(kind):
    inst = _inst()
    rng = random.Random(1)
    state = rng.getstate()
    assert set(draw_delays(inst, 0, rng, kind).values()) == {0}
    assert rng.getstate() == state


def test_both_kinds_have_the_same_mean():
    inst = _inst(n=40)
    means = {}
    for kind in C.DELAY_KINDS:
        rng = random.Random(11)
        vals = [v for _ in range(400) for v in draw_delays(inst, 8, rng, kind).values()]
        means[kind] = statistics.fmean(vals)
    assert means["exp"] == pytest.approx(8, rel=0.05)
    assert means["tail"] == pytest.approx(8, rel=0.08)


def test_tail_kind_has_about_eighty_percent_on_time_and_a_heavy_edge():
    inst = _inst(n=40)
    rng = random.Random(4)
    vals = [v for _ in range(400) for v in draw_delays(inst, 8, rng, "tail").values()]
    on_time = sum(1 for v in vals if v == 0) / len(vals)
    assert on_time == pytest.approx(0.8, abs=0.03)
    rng = random.Random(4)
    exp_vals = [v for _ in range(400) for v in draw_delays(inst, 8, rng, "exp").values()]
    assert max(vals) > max(exp_vals)
    assert statistics.pstdev(vals) > statistics.pstdev(exp_vals)


def test_exp_kind_is_much_less_often_on_time_than_tail():
    inst = _inst(n=40)
    rng = random.Random(9)
    vals = [v for _ in range(200) for v in draw_delays(inst, 8, rng, "exp").values()]
    assert sum(1 for v in vals if v == 0) / len(vals) < 0.2


def test_invalid_arguments_are_rejected():
    inst = _inst()
    with pytest.raises(ValueError):
        draw_delays(inst, 8, random.Random(0), "gleichverteilt")
    with pytest.raises(ValueError):
        draw_delays(inst, -1, random.Random(0), "exp")
    with pytest.raises(ValueError):
        buffered_instance(inst, -1)


def test_actual_arrivals_add_the_delay_to_the_eta():
    inst = _inst()
    d = scenario_delays(inst, 8, "exp", 1)
    act = actual_arrivals(inst, d)
    assert all(act[s.index] == s.arrival + d[s.index] for s in inst.ships)


def test_actual_instance_shifts_only_the_arrivals_and_keeps_the_horizon_sufficient():
    inst = _inst()
    d = {s.index: 40 + s.index for s in inst.ships}
    real = actual_instance(inst, d)
    for a, b in zip(inst.ships, real.ships):
        assert b.arrival == a.arrival + d[a.index]
        assert dataclasses.replace(b, arrival=a.arrival) == a
    assert real.zones == inst.zones and real.quay_length == inst.quay_length and real.safety_margin == inst.safety_margin
    assert real.horizon >= max(s.arrival for s in real.ships) + 24
    assert real.horizon >= inst.horizon
    assert actual_instance(inst, {s.index: 0 for s in inst.ships}) == inst


def test_buffered_instance_lengthens_every_berth_time_only():
    inst = _inst()
    buf = buffered_instance(inst, 3)
    for a, b in zip(inst.ships, buf.ships):
        assert b.handling_time == a.handling_time + 3
        assert dataclasses.replace(b, handling_time=a.handling_time) == a
    assert buffered_instance(inst, 0) == inst


def test_actual_instance_horizon_follows_the_formula_when_the_nominal_horizon_is_too_short():
    inst = dataclasses.replace(_inst(), horizon=1)
    d = {s.index: 10 for s in inst.ships}
    real = actual_instance(inst, d)
    assert real.horizon == sum(s.handling_time for s in inst.ships) + max(s.arrival for s in inst.ships) + 10 + 24
