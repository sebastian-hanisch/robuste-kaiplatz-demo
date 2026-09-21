import pytest

import rb_constants as C
import rb_exact
from berth_cp_solver import ExactResult
from berth_evaluation import check_feasible
from berth_heuristic import greedy_and_polish
from helpers import manual_instance, ship
from rb_delays import actual_instance, scenario_delays
from rb_exact import Clairvoyant, price_of_uncertainty, solve_clairvoyant
from rb_execution import run_reactive, run_static, weighted_wait
from rb_scenario import make_instance, valid_reference_instances

PORTS = list(C.REFERENCE_PRESETS)


def _cases(n_inst=3, seeds=(0, 1), deltas=(0, 4, 12)):
    for name in PORTS:
        for inst in valid_reference_instances(name, range(n_inst)):
            for kind in C.DELAY_KINDS:
                for delta in deltas:
                    for seed in seeds:
                        yield inst, scenario_delays(inst, delta, kind, seed)


# ---------------- Handgebaute Fälle mit bekanntem Optimum ----------------
def test_hand_case_clairvoyance_removes_all_waiting_when_the_delay_clears_the_quay():
    inst = manual_instance([ship(0, 100, 0, 10), ship(1, 100, 5, 10, "Mainliner", 3.0)])
    ex = solve_clairvoyant(inst, {0: 20, 1: 0})
    assert ex.proven and ex.source == "CP-SAT"
    assert ex.weighted_wait == 0
    assert ex.starts == {0: 20, 1: 5}


def test_hand_case_heavy_ship_goes_first_when_both_arrive_together():
    inst = manual_instance([ship(0, 100, 0, 10), ship(1, 100, 0, 10, "Mainliner", 3.0)])
    ex = solve_clairvoyant(inst, {0: 0, 1: 0})
    assert ex.proven
    assert ex.weighted_wait == 10.0                       # das leichte Schiff wartet 10 h mit Gewicht 1
    assert ex.starts == {0: 10, 1: 0}


def test_hand_case_two_ships_fit_side_by_side_and_do_not_wait():
    inst = manual_instance([ship(0, 40, 0, 10), ship(1, 40, 0, 10)], quay_length=100)
    ex = solve_clairvoyant(inst, {0: 0, 1: 0})
    assert ex.weighted_wait == 0 and ex.starts == {0: 0, 1: 0}
    assert abs(ex.positions[0] - ex.positions[1]) >= 40


def test_hand_case_a_delayed_ship_is_measured_from_its_actual_arrival():
    inst = manual_instance([ship(0, 100, 0, 10)])
    ex = solve_clairvoyant(inst, {0: 50})
    assert ex.starts == {0: 50} and ex.weighted_wait == 0


# ---------------- Eigenschaften ----------------
def test_clairvoyant_plan_is_feasible_proven_and_its_cost_is_consistent():
    n = 0
    for inst, d in _cases():
        ex = solve_clairvoyant(inst, d)
        real = actual_instance(inst, d)
        ok, viol = check_feasible(real, ex.plan)
        assert ok, viol
        assert ex.proven and ex.source == "CP-SAT"
        arrivals = {s.index: s.arrival for s in real.ships}
        assert ex.weighted_wait == pytest.approx(weighted_wait(inst, ex.starts, arrivals))
        assert all(ex.starts[i] >= arrivals[i] for i in arrivals)
        n += 1
    assert n >= 50


def test_clairvoyant_cost_is_a_lower_bound_of_every_strategy_and_of_the_plain_heuristic():
    n = 0
    for inst, d in _cases(n_inst=2, deltas=(0, 6, 12)):
        ex = solve_clairvoyant(inst, d)
        real = actual_instance(inst, d)
        heuristic = greedy_and_polish(real, seed=0, max_moves=C.STATIC_PLAN_MAX_MOVES)
        assert ex.weighted_wait <= sum(s.weight * (heuristic[s.index][0] - s.arrival) for s in real.ships) + 1e-9
        for run in (run_static(inst, d), run_static(inst, d, buffer_h=2), run_reactive(inst, d, 1), run_reactive(inst, d, 6)):
            assert ex.weighted_wait <= weighted_wait(inst, run.starts, run.arrivals) + 1e-9
            assert price_of_uncertainty(weighted_wait(inst, run.starts, run.arrivals), ex) >= 0
            n += 1
    assert n >= 100


def test_the_optimum_value_is_reproducible():
    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 3)
    a, b = solve_clairvoyant(inst, d), solve_clairvoyant(inst, d)
    assert a.proven and b.proven and a.weighted_wait == pytest.approx(b.weighted_wait)


def test_clairvoyant_cost_falls_with_delay_because_delays_decongest_the_quay():
    # Befund der Messreihe: gezählt wird nur die Wartezeit im Hafen, verspätete Ankünfte entzerren den Kai
    means = {}
    for delta in (0, 12):
        vals = []
        for inst in valid_reference_instances("Volle Kaikapazität", range(6)):
            for seed in range(3):
                vals.append(solve_clairvoyant(inst, scenario_delays(inst, delta, "exp", seed)).weighted_wait)
        means[delta] = sum(vals) / len(vals)
    assert means[12] < means[0]


def test_huge_delays_still_give_a_proven_solution():
    inst = make_instance()
    ex = solve_clairvoyant(inst, {s.index: 300 for s in inst.ships})
    assert ex.proven and min(ex.starts.values()) >= 300


def test_ten_ships_are_solved_to_proven_optimality_quickly():
    inst = make_instance(n_ships=10, seed=7)
    ex = solve_clairvoyant(inst, scenario_delays(inst, 8, "exp", 1))
    assert ex.proven and ex.wall_time_ms < 5000


# ---------------- Zeitlimit und Kennzeichnung "nicht bewiesen" ----------------
def test_a_tiny_time_limit_never_yields_a_wrong_or_better_than_optimal_result():
    inst = make_instance(n_ships=10, seed=7)
    d = scenario_delays(inst, 8, "exp", 1)
    optimum = solve_clairvoyant(inst, d)
    quick = solve_clairvoyant(inst, d, time_limit_seconds=0.001)
    assert check_feasible(actual_instance(inst, d), quick.plan)[0]
    assert quick.weighted_wait >= optimum.weighted_wait - 1e-9
    if quick.proven:
        assert quick.weighted_wait == pytest.approx(optimum.weighted_wait)


def _fake_solver(monkeypatch, result, calls=None):
    def fake(instance, time_limit_seconds=10, hint_plan=None):
        if calls is not None:
            calls.append((instance, time_limit_seconds, hint_plan))
        return result(instance, hint_plan)
    monkeypatch.setattr(rb_exact, "solve_exact", fake)


def test_result_without_optimality_proof_is_flagged_not_proven(monkeypatch):
    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 1)
    _fake_solver(monkeypatch, lambda i, h: ExactResult(True, False, h, 123.0, 5.0))
    ex = solve_clairvoyant(inst, d)
    assert ex.source == "CP-SAT" and not ex.proven


def test_no_solution_within_the_time_limit_falls_back_to_the_heuristic_and_is_flagged(monkeypatch):
    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 1)
    _fake_solver(monkeypatch, lambda i, h: ExactResult(False, False, {}, 0.0, 7.0))
    ex = solve_clairvoyant(inst, d)
    assert ex.source == "Heuristik" and not ex.proven
    assert ex.plan == greedy_and_polish(actual_instance(inst, d), seed=0, max_moves=C.STATIC_PLAN_MAX_MOVES)
    assert ex.wall_time_ms == 7.0


def test_the_solver_gets_the_time_limit_the_actual_instance_and_a_feasible_hint(monkeypatch):
    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 1)
    calls = []
    _fake_solver(monkeypatch, lambda i, h: ExactResult(True, True, h, 0.0, 1.0), calls)
    solve_clairvoyant(inst, d, time_limit_seconds=3)
    solve_clairvoyant(inst, d)
    (real, limit, hint), (_, default_limit, _) = calls
    assert real == actual_instance(inst, d) and limit == 3 and default_limit == C.EXACT_TIME_LIMIT_SECONDS
    assert check_feasible(real, hint)[0]


def test_an_infeasible_solver_plan_is_rejected_loudly(monkeypatch):
    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 1)
    _fake_solver(monkeypatch, lambda i, h: ExactResult(True, True, {s.index: (0, 0) for s in i.ships}, 0.0, 1.0))
    with pytest.raises(RuntimeError):
        solve_clairvoyant(inst, d)


def test_price_of_uncertainty_is_the_gap_and_never_negative_when_not_proven():
    proven = Clairvoyant({}, {}, 100.0, True, "CP-SAT", 1.0)
    unproven = Clairvoyant({}, {}, 100.0, False, "CP-SAT", 1.0)
    assert price_of_uncertainty(130.0, proven) == 30.0
    assert price_of_uncertainty(130.0, unproven) == 30.0
    assert price_of_uncertainty(80.0, unproven) == 0.0          # Strategie besser als die (nicht bewiesene) Lösung: wahrer Preis unbekannt
    assert price_of_uncertainty(100.0, proven) == 0.0
    assert price_of_uncertainty(90.0, proven) == -10.0          # bei bewiesenem Optimum bleibt ein negativer Preis sichtbar (er wäre ein Fehler)


def test_clairvoyant_plan_property():
    ex = Clairvoyant({0: 3, 1: 5}, {0: 10, 1: 20}, 0.0, True, "CP-SAT", 0.0)
    assert ex.plan == {0: (3, 10), 1: (5, 20)}
