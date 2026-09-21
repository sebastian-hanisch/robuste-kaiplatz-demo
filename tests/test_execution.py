import dataclasses
import random

import pytest

import rb_constants as C
from berth_cp_solver import solve_exact
from berth_evaluation import check_feasible
from helpers import manual_instance, ship
from rb_delays import actual_arrivals, actual_instance, scenario_delays
from rb_execution import (Execution, plan_on_etas, replan, replan_fast, right_shift, run_reactive, run_static,
                          wait_per_ship, weighted_wait)
from rb_scenario import make_instance, reference_instance, valid_reference_instances

REF = "Volle Kaikapazität"
PORTS = list(C.REFERENCE_PRESETS)


def _cases(n_inst=4, seeds=(0, 1, 2), deltas=(0, 3, 10)):
    """Instanzen aller Referenz-Häfen x Arten x Verspätungen x Seeds."""
    for name in PORTS:
        for inst in valid_reference_instances(name, range(n_inst)):
            for kind in C.DELAY_KINDS:
                for delta in deltas:
                    for seed in seeds:
                        yield inst, scenario_delays(inst, delta, kind, seed)


def _all_runs(inst, d):
    yield "starr", run_static(inst, d)
    yield "puffer", run_static(inst, d, buffer_h=2)
    yield "neuplanung", run_reactive(inst, d, 1)
    yield "prognose", run_reactive(inst, d, 6)


# ---------------- Unabhängiges Kontrollmodell der Rechts-Verschiebung ----------------
def control_right_shift(inst, plan, arrivals):
    """Ereignissimulation Stunde für Stunde statt Vorgängerschleife: ein Schiff legt an, sobald (a) seine tatsächliche Ankunft und sein geplantes Fenster
    erreicht sind und (b) jeder in der Planreihenfolge VOR ihm liegende, räumlich überlappende Vorgänger schon angelegt UND wieder abgelegt hat."""
    order = sorted(plan, key=lambda i: (plan[i][0], i))
    rank = {i: k for k, i in enumerate(order)}

    def overlap(i, j):
        wi, wj = inst.occupied_width(inst.ships[i]), inst.occupied_width(inst.ships[j])
        return plan[i][1] < plan[j][1] + wj and plan[j][1] < plan[i][1] + wi

    started = {}
    t = 0
    while len(started) < len(plan):
        for i in order:
            if i in started or t < arrivals[i] or t < plan[i][0]:
                continue
            preds = [j for j in plan if rank[j] < rank[i] and overlap(i, j)]
            if all(j in started and started[j] + inst.ships[j].handling_time <= t for j in preds):
                started[i] = t
        t += 1
        assert t < 100_000
    return started


def test_right_shift_matches_the_independent_control_model():
    n = 0
    for inst, d in _cases():
        act = actual_arrivals(inst, d)
        for buffer_h in (0, 3):
            from rb_delays import buffered_instance
            plan = plan_on_etas(buffered_instance(inst, buffer_h) if buffer_h else inst)
            assert right_shift(inst, plan, act) == control_right_shift(inst, plan, act)
            n += 1
    assert n > 200


# ---------------- Zulässigkeit gegen die WIRKLICHE Lage ----------------
def test_every_executed_plan_is_feasible_against_the_actual_arrivals():
    n = 0
    for inst, d in _cases(n_inst=3, seeds=(0, 1), deltas=(0, 4, 12)):
        real = actual_instance(inst, d)
        for label, ex in _all_runs(inst, d):
            ok, viol = check_feasible(real, ex.plan)
            assert ok, (label, viol)
            assert all(ex.starts[s.index] >= ex.arrivals[s.index] for s in inst.ships)
            n += 1
    assert n > 200


def test_no_ship_ever_starts_before_its_actual_arrival_and_waiting_is_never_negative():
    for inst, d in _cases(n_inst=2, seeds=(0,), deltas=(6,)):
        for label, ex in _all_runs(inst, d):
            assert min(ex.starts[i] - ex.arrivals[i] for i in ex.starts) >= 0
            assert wait_per_ship(inst, ex) >= 0


def test_static_never_starts_before_the_planned_window():
    for inst, d in _cases(n_inst=3, seeds=(0, 1), deltas=(0, 5)):
        plan = plan_on_etas(inst)
        ex = run_static(inst, d, plan=plan)
        assert all(ex.starts[i] >= plan[i][0] for i in plan)
        assert ex.positions == {i: plan[i][1] for i in plan}


def test_without_delays_static_is_exactly_the_plan_and_buffer_zero_equals_static():
    for name in PORTS:
        for inst in valid_reference_instances(name, range(6)):
            d = {s.index: 0 for s in inst.ships}
            plan = plan_on_etas(inst)
            ex = run_static(inst, d)
            assert ex.plan == plan and ex.announced == plan and ex.replans == 0
            assert run_static(inst, d, buffer_h=0) == ex


def test_puffer_costs_something_even_when_everybody_is_on_time_on_average():
    # der Puffer verlängert die Belegung im PLAN; über viele Instanzen ohne Verspätung wartet man dadurch im Mittel länger
    diffs = []
    for name in PORTS:
        for inst in valid_reference_instances(name, range(12)):
            d = {s.index: 0 for s in inst.ships}
            diffs.append(wait_per_ship(inst, run_static(inst, d, buffer_h=4)) - wait_per_ship(inst, run_static(inst, d)))
    assert sum(diffs) / len(diffs) > 0


def test_a_given_plan_is_used_as_is():
    inst = make_instance()
    d = scenario_delays(inst, 5, "exp", 1)
    plan = plan_on_etas(inst)
    assert run_static(inst, d, plan=plan) == run_static(inst, d)


# ---------------- Handgebaute Fälle mit bekannten Zahlen ----------------
def _duel():
    """Ein Liegeplatz für alles. A (Tramp, Gewicht 1, ETA 0) ist 20 h zu spät; B (Mainliner, Gewicht 3, ETA 5) ist pünktlich."""
    inst = manual_instance([ship(0, 100, 0, 10), ship(1, 100, 5, 10, "Mainliner", 3.0)])
    return inst, {0: 20, 1: 0}, {0: (0, 0), 1: (10, 0)}


def test_hand_case_static_waits_behind_the_late_ship():
    inst, d, plan = _duel()
    ex = run_static(inst, d, plan=plan)
    assert ex.starts == {0: 20, 1: 30}                    # B wartet auf den Vorgänger A, der erst um 20 kommt und um 30 fertig ist
    assert weighted_wait(inst, ex.starts, ex.arrivals) == 3.0 * (30 - 5) + 1.0 * 0
    assert ex.window_shift() == (20 + 20) / 2 and ex.position_changes() == 0


def test_hand_case_reactive_lets_the_punctual_ship_go_first():
    inst, d, _ = _duel()
    ex = run_reactive(inst, d, 1)
    assert ex.starts == {0: 20, 1: 5}                     # B legt sofort an, A kommt um 20, B ist um 15 fertig
    assert weighted_wait(inst, ex.starts, ex.arrivals) == 0
    assert ex.replans >= 2


def test_hand_case_reactive_replans_when_a_planned_window_passes_without_the_ship():
    inst = manual_instance([ship(0, 100, 0, 4)])
    ex = run_reactive(inst, {0: 9}, 1)
    assert ex.starts == {0: 9}
    assert ex.announced[0][0] == 1                        # angekündigt: ETA 0, aber nicht vor jetzt+1
    assert ex.replans >= 2                                # Anfang, dann mindestens einmal weil das Fenster verstrich, dann bei der Ankunft
    assert ex.window_shift() == 8


def test_hand_case_forecast_moves_unarrived_ships_into_the_future():
    inst = manual_instance([ship(0, 100, 0, 10), ship(1, 100, 1, 10)])
    d = {0: 0, 1: 29}                                     # tatsächliche Ankunft von Schiff 2: 1 + 29 = 30
    plain = run_reactive(inst, d, 1)
    forecast = run_reactive(inst, d, 20)
    assert plain.announced[1][0] == 10 and forecast.announced[1][0] == 20    # zweites Schiff: ETA 1, angekündigt 10 gegen 20 (t=0 + r=20)
    assert plain.starts == forecast.starts == {0: 0, 1: 30}


def test_hand_case_a_given_plan_that_differs_from_the_computed_one_is_executed():
    inst, d, _ = _duel()
    given = {1: (5, 0), 0: (15, 0)}                       # B zuerst, dann A: nicht das, was die Heuristik plant
    ex = run_static(inst, d, plan=given)
    assert ex.announced == given and ex.positions == {0: 0, 1: 0}
    assert ex.starts == {0: 20, 1: 5}                     # B pünktlich um 5 (fertig 15), A kommt um 20 und liegt sofort


def test_right_shift_uses_the_safety_margin_for_spatial_overlap():
    # zwei Schiffe der Länge 50, Abstand der Positionen 60: mit Sicherheitsabstand 20 (Breite 70) überlappen sie räumlich, ohne (Breite 50) nicht
    ships = [ship(0, 50, 0, 10), ship(1, 50, 0, 10)]
    plan = {0: (0, 0), 1: (0, 60)}
    assert right_shift(manual_instance(ships, quay_length=200, safety_margin=20), plan, {0: 0, 1: 0}) == {0: 0, 1: 10}
    assert right_shift(manual_instance(ships, quay_length=200, safety_margin=0), plan, {0: 0, 1: 0}) == {0: 0, 1: 0}
    # Grenzfall: Positionen genau eine Breite auseinander sind kein Überlapp
    assert right_shift(manual_instance(ships, quay_length=200, safety_margin=20), {0: (0, 0), 1: (0, 70)}, {0: 0, 1: 0}) == {0: 0, 1: 0}


def test_expected_delay_below_one_is_rejected():
    inst = manual_instance([ship(0, 100, 0, 4)])
    with pytest.raises(ValueError):
        run_reactive(inst, {0: 0}, 0)


# ---------------- Neuplanung: Invarianten je Ereignis ----------------
class _Auditor:
    """Ersatz-Neuplaner, der bei JEDEM Ereignis die Invarianten prüft und dann den echten aufruft."""

    def __init__(self, inner):
        self.inner, self.calls, self.prev_fixed = inner, 0, {}

    def __call__(self, inst_eff, fixed, remaining, max_moves):
        self.calls += 1
        n = len(inst_eff.ships)
        assert set(fixed).isdisjoint(remaining) and len(fixed) + len(remaining) == n     # jedes Schiff genau in einer der beiden Gruppen
        assert all(self.prev_fixed[i] == fixed[i] for i in self.prev_fixed)                # liegende Schiffe ändern sich nie
        self.prev_fixed = dict(fixed)
        plan = self.inner(inst_eff, fixed, remaining, max_moves)
        assert set(plan) == set(range(n))
        assert all(plan[i] == fixed[i] for i in fixed)                                     # Hindernisse respektiert
        assert all(plan[i][0] >= inst_eff.ships[i].arrival for i in remaining)             # nichts wird in die Vergangenheit geplant
        ok, viol = check_feasible(inst_eff, plan)
        assert ok, viol
        return plan


def test_replan_invariants_hold_at_every_event_and_replans_are_counted():
    total = 0
    for inst, d in _cases(n_inst=3, seeds=(0, 1), deltas=(0, 4, 12)):
        for r in (1, 6):
            aud = _Auditor(replan_fast)
            ex = run_reactive(inst, d, r, replanner=aud)
            assert ex.replans == aud.calls >= 1
            total += aud.calls
    assert total > 500


def test_replan_fast_returns_exactly_the_reference_replan():
    n = 0
    for inst, d in _cases(n_inst=3, seeds=(0, 1), deltas=(4, 12)):
        rng = random.Random(len(inst.ships))
        arrivals = actual_arrivals(inst, d)
        # Zustand mitten im Ablauf: einige Schiffe liegen (aus einem starren Plan), der Rest wird neu eingeplant
        plan = plan_on_etas(inst)
        starts = right_shift(inst, plan, arrivals)
        k = rng.randint(0, len(inst.ships) - 1)
        fixed_ids = sorted(starts, key=lambda i: (starts[i], i))[:k]
        fixed = {i: (starts[i], plan[i][1]) for i in fixed_ids}
        rest = [i for i in range(len(inst.ships)) if i not in fixed]
        eff = dataclasses.replace(inst, ships=tuple(
            dataclasses.replace(s, arrival=arrivals[s.index]) if s.index in rest else s for s in inst.ships))
        for moves in (0, 1, 2, 5, C.REPLAN_MAX_MOVES):
            assert replan_fast(eff, fixed, rest, moves) == replan(eff, fixed, rest, moves), moves
        n += 1
    assert n > 50


def test_replan_without_search_is_the_better_of_the_two_start_orders():
    from rb_execution import _score_remaining
    n = 0
    for inst, d in _cases(n_inst=6, seeds=(0, 1), deltas=(6,)):
        arrivals = actual_arrivals(inst, d)
        eff = dataclasses.replace(inst, ships=tuple(dataclasses.replace(s, arrival=arrivals[s.index]) for s in inst.ships))
        rest = list(range(len(inst.ships)))
        by_arrival = sorted(rest, key=lambda i: (eff.ships[i].arrival, i))
        by_weight = sorted(rest, key=lambda i: (-eff.ships[i].weight, eff.ships[i].arrival, i))
        best = min(_score_remaining(eff, {}, by_arrival)[0], _score_remaining(eff, {}, by_weight)[0])
        plan = replan(eff, {}, rest, 0)
        assert sum(eff.ships[i].weight * (plan[i][0] - eff.ships[i].arrival) for i in rest) == pytest.approx(best)
        n += 1
    assert n > 20


def test_replan_search_moves_matter_and_zero_moves_is_the_plain_insertion():
    inst = make_instance()
    eff = dataclasses.replace(inst, ships=tuple(dataclasses.replace(s, arrival=s.arrival + (7 * s.index) % 11) for s in inst.ships))
    rest = list(range(len(inst.ships)))
    cost0 = sum(s.weight * (replan(eff, {}, rest, 0)[s.index][0] - s.arrival) for s in eff.ships)
    cost40 = sum(s.weight * (replan(eff, {}, rest, 40)[s.index][0] - s.arrival) for s in eff.ships)
    assert cost40 <= cost0


# ---------------- Ergebnisobjekt ----------------
def test_execution_metrics_on_a_hand_built_result():
    ex = Execution(starts={0: 10, 1: 7}, positions={0: 0, 1: 200}, announced={0: (6, 0), 1: (9, 100)}, replans=3,
                   arrivals={0: 4, 1: 5})
    assert ex.plan == {0: (10, 0), 1: (7, 200)}
    assert ex.position_changes() == 1
    assert ex.window_shift() == (4 + 2) / 2               # +4 und -2: Beträge, nicht Vorzeichen
    inst = manual_instance([ship(0, 50, 4, 5, weight=1.5), ship(1, 50, 5, 5, weight=2.0)])
    assert weighted_wait(inst, ex.starts, ex.arrivals) == 1.5 * 6 + 2.0 * 2
    assert wait_per_ship(inst, ex) == (1.5 * 6 + 2.0 * 2) / 2


def test_static_plans_never_change_positions_and_reactive_changes_few():
    changes = []
    for inst, d in _cases(n_inst=3, seeds=(0,), deltas=(8,)):
        assert run_static(inst, d).position_changes() == 0
        changes.append(run_reactive(inst, d, 1).position_changes() / len(inst.ships))
    assert sum(changes) / len(changes) < 0.5           # Befund der Messreihe: Positionen ändern sich kaum, Zeitfenster sehr wohl


# ---------------- Feste Werte der Vorab-Messreihe ----------------
# Gewichtete Wartezeit je Szenario (Gesamtkosten): starr, Puffer 2 h, Neuplanung r=1, Neuplanung+Prognose r=8.
# Volle Kaikapazität, Instanzen 0..4 (Seeds 0..), gleichmäßige Verspätung Mittel 8 h, Verspätungs-Seed 0/1.
# Stimmt mit dem Code der Messreihe (hafen-planung/messreihe_kai/robust.py) überein (288 Einzelvergleiche ohne Abweichung).
REFERENCE = {
    (0, 0): (124.0, 129.5, 187.5, 134.0), (0, 1): (168.5, 169.5, 117.5, 197.5),
    (1, 0): (314.5, 265.5, 247.5, 249.0), (1, 1): (264.5, 301.5, 264.5, 238.5),
    (2, 0): (130.5, 119.0, 103.0, 92.0), (2, 1): (154.0, 135.0, 69.5, 60.5),
    (3, 0): (140.5, 147.5, 216.5, 140.5), (3, 1): (167.0, 168.0, 215.5, 168.5),
    (4, 0): (343.0, 343.0, 258.0, 258.0), (4, 1): (140.0, 190.0, 140.0, 140.0),
}


def test_reference_values_of_the_measurement_series_are_reproduced():
    insts = valid_reference_instances(REF, range(120))[:5]
    for (k, seed), expected in REFERENCE.items():
        inst = insts[k]
        d = scenario_delays(inst, 8, "exp", seed)
        got = tuple(weighted_wait(inst, e.starts, e.arrivals) for e in (
            run_static(inst, d), run_static(inst, d, buffer_h=2), run_reactive(inst, d, 1), run_reactive(inst, d, 8)))
        assert got == expected, (k, seed)


def test_reactive_beats_static_on_average_but_not_in_every_scenario():
    # Befund der Messreihe: im Mittel besser, im Einzelfall oft schlechter ("Mittelwerte täuschen")
    gains = []
    for inst in valid_reference_instances(REF, range(8)):
        for seed in range(4):
            d = scenario_delays(inst, 8, "exp", seed)
            gains.append(weighted_wait(inst, *(lambda e: (e.starts, e.arrivals))(run_static(inst, d)))
                         - weighted_wait(inst, *(lambda e: (e.starts, e.arrivals))(run_reactive(inst, d, 8))))
    assert sum(gains) / len(gains) > 0
    assert any(g < 0 for g in gains) and any(g > 0 for g in gains)


# ---------------- Zusammenspiel mit dem Exakt-Löser (Hellsehen) ----------------
def test_clairvoyant_optimum_is_a_lower_bound_of_every_strategy():
    n = 0
    for name in PORTS:
        for inst in valid_reference_instances(name, range(3)):
            for kind in C.DELAY_KINDS:
                d = scenario_delays(inst, 8, kind, 1)
                real = actual_instance(inst, d)
                opt = solve_exact(real, time_limit_seconds=10)
                assert opt.feasible and opt.optimal
                for label, ex in _all_runs(inst, d):
                    assert opt.total_weighted_wait <= weighted_wait(inst, ex.starts, ex.arrivals) + 1e-9, label
                    n += 1
    assert n >= 40


def test_actual_instance_is_solvable_by_the_exact_solver_even_for_huge_delays():
    inst = reference_instance(REF, 7)
    d = {s.index: 200 for s in inst.ships}
    assert solve_exact(actual_instance(inst, d), time_limit_seconds=10).feasible
