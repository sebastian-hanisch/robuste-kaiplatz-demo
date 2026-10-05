"""Unabhängige Orakel (anderer Rechenweg als der Demo-Code), klein und schnell.

* Hellsehen: vollständige Aufzählung (Reihenfolge, Position, frühester Start) auf Mini-Instanzen statt CP-SAT.
* Rechts-Verschiebung: stundenweise Ereignissimulation statt der Vorgängerschleife aus `rb_execution`.
"""

import random

import pytest

import rb_exact
from berth_evaluation import check_feasible
from berth_scenario import generate_instance
from rb_delays import actual_arrivals, actual_instance, scenario_delays
from rb_execution import run_reactive, run_static, weighted_wait
from rb_scenario import is_playable, make_instance

INF = float("inf")


def _tiny(rng):
    return generate_instance(
        n_ships=rng.choice([2, 3, 3, 4]), quay_length=rng.choice([140, 180, 220, 300]), deep_zone_fraction=rng.choice([0.4, 0.5, 0.6]),
        deep_draft_limit=15.0, length_avg=rng.choice([50, 70, 90]), length_variability=0.25, draft_avg=rng.choice([6.0, 9.0, 11.0]),
        draft_variability=0.2, handling_avg=rng.choice([3, 5, 8]), handling_variability=0.3, arrival_spread=rng.choice([0, 3, 8]),
        mainliner_fraction=rng.choice([0.0, 0.4, 0.7]), safety_margin=rng.choice([5, 10]), seed=rng.randint(0, 10 ** 6))


def _brute_optimum(inst):
    """Minimum der gewichteten Wartezeit über alle Reihenfolgen, Positionen und frühesten zulässigen Starts."""
    ships, n = inst.ships, len(inst.ships)
    occ = [inst.occupied_width(s) for s in ships]
    cand = []
    for i, s in enumerate(ships):
        sums = {0}
        for j in range(n):
            if j != i:
                sums |= {x + occ[j] for x in sums}
        cand.append(sorted({z.start + x for z in inst.compatible_zones(s) for x in sums if z.start + x + occ[i] <= z.end}))
    best = [INF]

    def dfs(placed, remaining, cost):
        if cost >= best[0]:
            return
        if not remaining:
            best[0] = cost
            return
        for i in sorted(remaining):
            s = ships[i]
            for p in cand[i]:
                clash = [(j, tj) for (j, pj, tj) in placed if pj < p + occ[i] and p < pj + occ[j]]
                for t in sorted({s.arrival} | {tj + ships[j].handling_time for j, tj in clash if tj + ships[j].handling_time >= s.arrival}):
                    if all(not (tj < t + s.handling_time and t < tj + ships[j].handling_time) for j, tj in clash):
                        dfs(placed + [(i, p, t)], remaining - {i}, cost + s.weight * (t - s.arrival))
                        break

    dfs([], frozenset(range(n)), 0.0)
    return best[0]


def _hourly_right_shift(inst, announced, arrivals):
    order = sorted(announced, key=lambda i: (announced[i][0], i))
    started, pending, t = {}, list(order), 0
    while pending:
        for i in list(pending):
            if t < arrivals[i] or t < announced[i][0]:
                continue
            blocked = False
            for j in order:
                if j == i:
                    break
                pj, pi = announced[j][1], announced[i][1]
                if pi < pj + inst.occupied_width(inst.ships[j]) and pj < pi + inst.occupied_width(inst.ships[i]):
                    if j not in started or started[j] + inst.ships[j].handling_time > t:
                        blocked = True
                        break
            if not blocked:
                started[i] = t
                pending.remove(i)
        t += 1
        assert t < 10000
    return started


def test_hand_case_brute_force():
    from berth_scenario import Instance, Ship, Zone
    ships = (Ship(0, "a", 40, 5.0, 0, 4, "Tramp", 1.0), Ship(1, "b", 40, 5.0, 0, 4, "Mainliner", 3.0), Ship(2, "c", 40, 5.0, 0, 4, "Tramp", 1.0))
    inst = Instance(quay_length=100, zones=(Zone("A", 0, 100, 10.0),), ships=ships, safety_margin=10, horizon=50)
    assert _brute_optimum(inst) == 4.0     # zwei liegen nebeneinander, das dritte (leichteste) wartet 4 h


def test_clairvoyant_matches_enumeration_and_strategies_never_beat_it():
    rng = random.Random(31)
    checked = 0
    while checked < 25:
        inst = _tiny(rng)
        if inst.is_trivially_infeasible():
            continue
        d = scenario_delays(inst, rng.choice([0, 2, 5, 10]), rng.choice(["exp", "tail"]), rng.randint(0, 99))
        real = actual_instance(inst, d)
        opt = _brute_optimum(real)
        res = rb_exact.solve_clairvoyant(inst, d, 20)
        assert res.proven and res.weighted_wait == pytest.approx(opt)
        for ex in (run_static(inst, d), run_reactive(inst, d, 1), run_reactive(inst, d, 3)):
            assert check_feasible(real, ex.plan)[0]
            assert weighted_wait(inst, ex.starts, ex.arrivals) >= opt - 1e-9
        checked += 1


def test_right_shift_matches_hourly_simulation():
    rng = random.Random(32)
    checked = 0
    while checked < 40:
        inst = make_instance(rng.randint(2, 9), rng.choice([500, 600, 800]), rng.choice([12, 30, 60]), rng.choice([8, 14, 24]),
                             rng.choice([0.0, 0.3, 0.6]), rng.randint(0, 9999))
        if not is_playable(inst):
            continue
        d = scenario_delays(inst, rng.choice([0, 3, 8, 16]), rng.choice(["exp", "tail"]), rng.randint(0, 999))
        ex = run_static(inst, d, buffer_h=rng.choice([0, 1, 4]))
        assert _hourly_right_shift(inst, ex.announced, actual_arrivals(inst, d)) == ex.starts
        checked += 1
