import math
import statistics

import pytest

import rb_constants as C
from helpers import manual_instance, ship
from rb_delays import scenario_delays
from rb_evaluation import (KeyFigures, SweepResult, buffer_tipping_point, comparison_rows, delay_sweep, distribution, draw_seed,
                           forecast_hours, key_figures, outcome_of, run_strategies, static_plans, sweep_instances, verdict)
from rb_execution import run_static, weighted_wait
from rb_scenario import make_instance

S, P, N, F, X = C.STRAT_STARR, C.STRAT_PUFFER, C.STRAT_NEU, C.STRAT_PROGNOSE, C.STRAT_EXACT
ARGS = (9, 600, 30, 14, 0.3)          # Schiffe, Kailänge, Ankunftsfenster, Liegezeit, Mainliner-Anteil


def fake_sweep(deltas, series, n_ships=10, kind="exp"):
    """Handgebauter Sweep: series[key] = Liste (je delta) von Listen (je Szenario) mit Gesamtkosten."""
    n = len(next(iter(series.values()))[0])
    return SweepResult(tuple(deltas), kind, n_ships, n, {k: tuple(tuple(v) for v in vs) for k, vs in series.items()}, 0)


# ---------------- Prognose in Stunden ----------------
def test_forecast_hours():
    assert forecast_hours(8, 100) == 8
    assert forecast_hours(8, 200) == 16
    assert forecast_hours(8, 50) == 4
    assert forecast_hours(8, 0) == 1                   # 0 % = nur die ETA
    assert forecast_hours(0, 100) == 1                 # keine Verspätung, aber nie unter 1
    assert forecast_hours(3, 10) == 1                  # 0,3 h -> mindestens 1
    assert forecast_hours(7, 150) == round(10.5)
    assert forecast_hours(5, 70) == 4                  # 3,5 wird gerundet, nicht abgeschnitten


# ---------------- Ein Szenario ----------------
def test_run_strategies_share_the_scenario_and_report_consistent_numbers():
    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 3)
    outs = run_strategies(inst, d, 8, 2, 100)
    assert [o.key for o in outs] == [S, P, N, F]
    for o in outs:
        assert o.label == C.STRATEGY_LABELS[o.key]
        assert o.wait_total == weighted_wait(inst, o.execution.starts, o.execution.arrivals)
        assert o.wait_per_ship == pytest.approx(o.wait_total / len(inst.ships))
        assert {s.priority for s in inst.ships} == set(o.wait_by_priority)
        assert all(v >= 0 for v in o.wait_by_priority.values())
        assert o.execution.arrivals == outs[0].execution.arrivals            # gleiche Verspätungen
    assert outcome_of(outs, S).wait_total == weighted_wait(inst, *(lambda e: (e.starts, e.arrivals))(run_static(inst, d)))
    assert outcome_of(outs, S).replans == 0 and outcome_of(outs, N).replans >= 1
    assert outcome_of(outs, S).position_changes == 0


def test_wait_by_priority_is_the_unweighted_mean_of_the_ships_of_that_priority():
    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 3)
    o = outcome_of(run_strategies(inst, d, 8, 1, 100), N)
    for prio, mean in o.wait_by_priority.items():
        waits = [o.execution.starts[s.index] - o.execution.arrivals[s.index] for s in inst.ships if s.priority == prio]
        assert mean == pytest.approx(statistics.fmean(waits))


def test_buffer_zero_is_identical_to_static_in_every_number():
    inst = make_instance()
    for seed in range(4):
        d = scenario_delays(inst, 8, "tail", seed)
        outs = run_strategies(inst, d, 8, 0, 100)
        a, b = outcome_of(outs, S), outcome_of(outs, P)
        assert a.execution.starts == b.execution.starts and a.wait_total == b.wait_total


def test_buffer_changes_the_plan_but_not_the_reference():
    inst = make_instance()
    d = {s.index: 0 for s in inst.ships}
    plans = static_plans(inst, 4)
    assert plans[0] != plans[1]
    assert static_plans(inst, 0)[1] is None
    outs = run_strategies(inst, d, 0, 4, 100, plans)
    assert outcome_of(outs, P).execution.announced == plans[1] and outcome_of(outs, S).execution.announced == plans[0]


def test_the_forecast_slider_moves_only_the_forecast_strategy():
    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 3)
    lo, hi = run_strategies(inst, d, 8, 1, 0), run_strategies(inst, d, 8, 1, 200)
    for key in (S, P, N):
        assert outcome_of(lo, key).execution.starts == outcome_of(hi, key).execution.starts
    assert outcome_of(lo, F).execution.announced != outcome_of(hi, F).execution.announced
    assert outcome_of(lo, F).execution.starts == outcome_of(lo, N).execution.starts      # 0 % Prognose = Neuplanung


def test_comparison_rows_use_mine_minus_reference():
    inst = make_instance()
    d = scenario_delays(inst, 12, "exp", 2)
    outs = run_strategies(inst, d, 12, 1, 100)
    rows = comparison_rows(outs)
    ref = outcome_of(outs, S).wait_total
    assert [r.key for r in rows] == [S, P, N, F]
    for r, o in zip(rows, outs):
        assert r.delta_vs_baseline == pytest.approx(o.wait_total - ref)
        assert r.delta_pct == pytest.approx(100 * (o.wait_total - ref) / ref)
        assert (r.replans, r.position_changes) == (o.replans, o.position_changes)
    assert rows[0].delta_vs_baseline == 0 and rows[0].delta_pct == 0


def test_comparison_rows_without_any_waiting_have_no_percentage():
    inst = manual_instance([ship(0, 50, 0, 5)])
    rows = comparison_rows(run_strategies(inst, {0: 0}, 0, 0, 100))
    assert all(r.wait_total == 0 and r.delta_vs_baseline == 0 and r.delta_pct is None for r in rows)


# ---------------- Handgebaute Kurven: Verteilung, Kipppunkt, Urteil, Kennzahlen ----------------
def test_distribution_counts_and_statistics_on_a_hand_built_sample():
    gains = [10, 3, 0.4, 0, -0.4, -0.5, -0.6, -2, 5, 0.5]         # Referenz - Strategie
    base = [100] * 10
    sw = fake_sweep((8,), {S: [base], N: [[b - g for b, g in zip(base, gains)]]})
    d = distribution(sw, N, 8)
    assert d.better == 0.3                                        # 10, 3, 5 (> 0,5); 0,4 und genau 0,5 zählen als gleich
    assert d.worse == 0.2                                         # -0,6 und -2 (< -0,5); -0,5 zählt als gleich
    assert d.equal == pytest.approx(0.5)
    assert d.mean_gain == pytest.approx(sum(gains) / 10) and d.median_gain == pytest.approx(statistics.median(gains))
    assert d.p90_gain == sorted(gains)[9]
    assert d.top10_share == pytest.approx(10 / 18.9)              # bester 1 von 10 Szenarien / gesamter positiver Gewinn (10+3+0,4+5+0,5)
    assert d.better + d.equal + d.worse == pytest.approx(1)


def test_distribution_without_positive_gain_has_no_top_share_and_the_baseline_ties_itself():
    sw = fake_sweep((8,), {S: [[10, 10, 10]], N: [[12, 11, 13]]})
    assert distribution(sw, N, 8).top10_share is None
    d = distribution(sw, S, 8)
    assert (d.better, d.equal, d.worse) == (0, 1, 0)


def test_distribution_shows_that_the_mean_can_deceive():
    base = [100] * 20
    gains = [0] * 18 + [-1, 200]                                  # ein Riesengewinn, sonst nichts
    sw = fake_sweep((8,), {S: [base], N: [[b - g for b, g in zip(base, gains)]]})
    d = distribution(sw, N, 8)
    assert d.mean_gain > 5 and d.median_gain == 0 and d.top10_share == 1.0 and d.better == 0.05


def test_top_share_counts_only_positive_gains_of_the_best_tenth():
    base = [100] * 20
    gains = [10, -1] + [-2] * 18                                  # bestes Zehntel = 2 Szenarien, nur eines davon ein Gewinn
    sw = fake_sweep((8,), {S: [base], N: [[b - g for b, g in zip(base, gains)]]})
    assert distribution(sw, N, 8).top10_share == 1.0


def test_distribution_uses_the_requested_delay_column():
    sw = fake_sweep((0, 8), {S: [[10, 10], [10, 10]], N: [[10, 10], [0, 0]]})
    assert distribution(sw, N, 0).better == 0 and distribution(sw, N, 8).better == 1
    assert distribution(sw, N, 7).better == 1                     # nächstes Rasterdelay


def test_buffer_tipping_point_is_interpolated_between_grid_points():
    # je Schiff (n_ships = 1): Puffer - starr = +3 bei 0, +1 bei 4, -1 bei 8  -> Vorzeichenwechsel bei 4 + 4 * 1/2 = 6
    sw = fake_sweep((0, 4, 8), {S: [[10], [10], [10]], P: [[13], [11], [9]]}, n_ships=1)
    assert buffer_tipping_point(sw) == pytest.approx(6.0)


def test_buffer_tipping_point_edge_cases():
    never = fake_sweep((0, 4, 8), {S: [[10], [10], [10]], P: [[13], [12], [11]]}, n_ships=1)
    assert buffer_tipping_point(never) is None
    always = fake_sweep((0, 4), {S: [[10], [10]], P: [[10], [9]]}, n_ships=1)
    assert buffer_tipping_point(always) == 0.0                    # schon ohne Verspätung nicht schlechter
    touching = fake_sweep((0, 4, 8), {S: [[10], [10], [10]], P: [[12], [10], [9]]}, n_ships=1)
    assert buffer_tipping_point(touching) == 4.0                  # Gleichstand zählt als "nicht mehr schlechter"
    with pytest.raises(ValueError):
        buffer_tipping_point(fake_sweep((2, 4), {S: [[10], [10]], P: [[12], [9]]}, n_ships=1))


def test_verdict_has_three_states_guarded_by_the_paired_standard_error():
    base = [100, 120, 90, 110, 100, 105, 95, 115]
    better = [b - 20 - (i % 3) for i, b in enumerate(base)]        # klar besser
    worse = [b + 20 + (i % 3) for i, b in enumerate(base)]
    noise = [b + (5 if i % 2 else -5) for i, b in enumerate(base)]  # Mittel 0, große Streuung
    sw = fake_sweep((8,), {S: [base], N: [better], P: [worse], F: [noise]}, n_ships=10)
    vb, vw, vn = verdict(sw, N, 8), verdict(sw, P, 8), verdict(sw, F, 8)
    assert (vb.kind, vw.kind, vn.kind) == ("better", "worse", "unclear")
    assert vb.diff < 0 < vw.diff and abs(vn.diff) <= C.VERDICT_Z * vn.se
    assert vb.diff == pytest.approx(statistics.fmean(x - b for x, b in zip(better, base)) / 10)      # je Schiff (10 Schiffe)
    assert vb.se == pytest.approx(statistics.stdev([(x - b) / 10 for x, b in zip(better, base)]) / math.sqrt(8))
    assert vb.pct == pytest.approx(100 * vb.diff / (statistics.fmean(base) / 10))
    assert vb.loss_share == 0 and vw.loss_share == 1.0


def test_verdict_is_unclear_when_the_difference_is_within_two_standard_errors_but_not_beyond():
    base = [0.0] * 8
    diffs = [3, -1, 3, -1, 3, -1, 3, -1]                            # Mittel 1,0, Verhältnis Differenz/Standardfehler ca. 1,3
    sw = fake_sweep((8,), {S: [base], N: [diffs]}, n_ships=1)
    v = verdict(sw, N, 8)
    se = statistics.stdev(diffs) / math.sqrt(8)
    assert v.diff == pytest.approx(1.0) and v.se == pytest.approx(se)
    assert v.kind == ("unclear" if abs(v.diff) <= C.VERDICT_Z * se else "worse")
    assert v.kind == "unclear"


def test_verdict_of_identical_series_is_unclear_and_has_no_percentage_without_cost():
    sw = fake_sweep((8,), {S: [[0, 0, 0]], N: [[0, 0, 0]]}, n_ships=1)
    v = verdict(sw, N, 8)
    assert v.kind == "unclear" and v.pct is None and v.diff == 0 and v.se == 0


def test_sweep_statistics_are_per_ship():
    sw = fake_sweep((0,), {S: [[10, 20, 30, 40]]}, n_ships=5)
    assert sw.mean(S, 0) == pytest.approx(25 / 5)
    assert sw.sem(S, 0) == pytest.approx(statistics.stdev([10, 20, 30, 40]) / 2 / 5)
    assert fake_sweep((0,), {S: [[7]]}).sem(S, 0) == 0.0
    assert sw.gains(S, 0) == (0, 0, 0, 0)


def test_key_figures_combine_curve_and_focus_sample():
    n = 1
    curve = fake_sweep((0, 4, 8), {S: [[10], [12], [20]], P: [[11], [12], [19]], N: [[10], [11], [15]], F: [[10], [11], [14]],
                                   X: [[9], [9], [8]]}, n_ships=n)
    focus = fake_sweep((8,), {S: [[20, 40]], P: [[18, 40]], N: [[16, 20]], F: [[10, 20]]}, n_ships=n)
    k = key_figures(curve, focus, 8)
    assert isinstance(k, KeyFigures) and k.delay == 8
    assert k.buffer_price_at_zero_pct == pytest.approx(10.0)                # Puffer 11 gegen starr 10 bei delay 0
    assert k.reactive_gain == pytest.approx(30 - 18) and k.reactive_gain_pct == pytest.approx(100 * 12 / 30)
    assert k.forecast_gain == pytest.approx(30 - 15) and k.forecast_gain_pct == pytest.approx(50.0)
    assert k.price_of_uncertainty == pytest.approx(20 - 8)                   # Kurve: starr - Hellsehen bei delay 8
    assert k.tipping_point == pytest.approx(4.0)                              # Puffer - starr: +1, 0, -1 -> Gleichstand bei 4


def test_key_figures_take_the_focus_values_at_the_focus_delay_not_the_curve():
    curve = fake_sweep((0, 8), {S: [[10], [10]], P: [[12], [10]], N: [[10], [10]], F: [[10], [10]], X: [[5], [5]]}, n_ships=1)
    focus = fake_sweep((8,), {S: [[100]], P: [[100]], N: [[70]], F: [[60]]}, n_ships=1)
    k = key_figures(curve, focus, 8)
    assert k.reactive_gain == 30 and k.forecast_gain == 40 and k.price_of_uncertainty == 5
    assert k.tipping_point == 8.0                                             # Puffer 12 -> 10 bei 8: Gleichstand am Rasterpunkt 8


def test_key_figures_pick_the_focus_column_of_the_requested_delay():
    curve = fake_sweep((0, 8), {S: [[10], [10]], P: [[12], [10]], N: [[10], [10]], F: [[10], [10]], X: [[5], [5]]}, n_ships=1)
    focus = fake_sweep((4, 8), {S: [[100], [100]], P: [[100], [100]], N: [[90], [70]], F: [[80], [60]]}, n_ships=1)
    k = key_figures(curve, focus, 8)
    assert k.reactive_gain == 30 and k.forecast_gain == 40


# ---------------- Die echte Kurve (klein) ----------------
def _small(**kw):
    args = dict(n_instances=4, n_draws=2, deltas=(0, 4, 8), with_exact=True)
    args.update(kw)
    return delay_sweep(*ARGS, "exp", 4, 1, 100, **args)


def test_delay_sweep_shape_grid_and_lower_bound():
    sw = _small()
    assert sw.deltas == (0, 4, 8) and sw.n_ships == 9 and sw.n_scenarios == 8 and sw.kind == "exp"
    assert set(sw.values) == set(C.STRATEGY_KEYS)
    assert all(len(v) == 3 and all(len(s) == 8 for s in v) for v in sw.values.values())
    for i in range(3):
        for key in (S, P, N, F):
            assert all(x <= y + 1e-9 for x, y in zip(sw.series(X, i), sw.series(key, i)))     # Hellsehen ist untere Schranke, gepaart je Szenario
    assert sw.unproven == 0


def test_the_current_delay_always_belongs_to_the_grid():
    sw = delay_sweep(*ARGS, "exp", 6, 1, 100, n_instances=3, n_draws=1, deltas=(4, 12), with_exact=False)
    assert sw.deltas == (4, 6, 12)                                          # eingestelltes delay wird eingefügt; 0 nur, wenn im Raster oder eingestellt
    sw0 = delay_sweep(*ARGS, "exp", 0, 1, 100, n_instances=3, n_draws=1, deltas=(4,), with_exact=False)
    assert sw0.deltas == (0, 4)
    with pytest.raises(ValueError):
        buffer_tipping_point(sw)


def test_delay_sweep_is_deterministic_and_at_zero_delay_the_buffer_plan_is_the_only_difference():
    a, b = _small(n_instances=3), _small(n_instances=3)
    assert a == b
    zero_puffer0 = delay_sweep(*ARGS, "exp", 0, 0, 100, n_instances=3, n_draws=2, deltas=(0,), with_exact=False)
    assert zero_puffer0.values[P] == zero_puffer0.values[S]                 # Puffer 0 h = starr, in jedem Szenario


def test_without_delay_static_and_buffer_costs_do_not_depend_on_the_delay_kind():
    a = delay_sweep(*ARGS, "exp", 0, 1, 100, n_instances=3, n_draws=2, deltas=(0,), with_exact=False)
    b = delay_sweep(*ARGS, "tail", 0, 1, 100, n_instances=3, n_draws=2, deltas=(0,), with_exact=False)
    assert a.values == b.values and a.kind != b.kind


def test_without_exact_the_four_executable_strategies_only():
    sw = _small(with_exact=False)
    assert X not in sw.values and set(sw.values) == {S, P, N, F} and sw.unproven == 0


def test_a_bigger_sample_contains_the_smaller_one_scenario_by_scenario():
    small = delay_sweep(*ARGS, "exp", 4, 1, 100, n_instances=3, n_draws=2, deltas=(4,), with_exact=False)
    big = delay_sweep(*ARGS, "exp", 4, 1, 100, n_instances=5, n_draws=3, deltas=(4,), with_exact=False)
    for key in (S, P, N, F):
        for k in range(3):
            for j in range(2):
                assert small.values[key][0][k * 2 + j] == big.values[key][0][k * 3 + j], (key, k, j)


def test_progress_is_reported_after_every_scenario_and_ends_at_one():
    seen = []
    delay_sweep(*ARGS, "exp", 4, 1, 100, n_instances=2, n_draws=2, deltas=(0, 4), with_exact=False, progress=seen.append)
    assert seen == pytest.approx([(i + 1) / 8 for i in range(8)])


def test_sweep_scenarios_use_the_documented_seeds_and_shared_random_numbers():
    inst = sweep_instances(*ARGS, 3)[2]
    assert draw_seed(2, 1) == 2001 and draw_seed(0, 0) == 0
    lo = scenario_delays(inst, 4, "exp", draw_seed(2, 1))
    hi = scenario_delays(inst, 8, "exp", draw_seed(2, 1))
    assert all(hi[i] >= lo[i] for i in lo) and any(hi[i] > lo[i] for i in lo)             # gemeinsame Zufallszahlen: mehr delta, mehr Verspätung


def test_sweep_instances_are_playable_independent_of_the_set_seed_and_unplayable_settings_fail():
    insts = sweep_instances(*ARGS, 6)
    assert len(insts) == 6 and len({i.ships for i in insts}) == 6
    assert insts == sweep_instances(*ARGS, 6)
    with pytest.raises(ValueError):
        sweep_instances(5, 100, 30, 14, 0.3, 3)                                  # Schiffe länger als der ganze Kai


def test_sweep_reproduces_the_orders_of_magnitude_of_the_measurement_series():
    sw = delay_sweep(*ARGS, "exp", 12, 1, 100, n_instances=10, n_draws=2, deltas=(0, 12), with_exact=False)
    i0, i12 = 0, 1
    assert sw.mean(S, i12) > sw.mean(S, i0)                                       # starr wird mit Verspätung deutlich teurer
    assert sw.mean(P, i0) > sw.mean(S, i0)                                        # Puffer kostet ohne Verspätung
    assert sw.mean(N, i12) < sw.mean(S, i12) and sw.mean(F, i12) < sw.mean(N, i12)


def test_sweep_first_instance_is_seed_zero_and_the_sweep_matches_direct_runs():
    from rb_evaluation import forecast_hours
    from rb_execution import plan_on_etas, run_reactive
    from rb_delays import buffered_instance
    assert sweep_instances(*ARGS, 2)[0] == make_instance(*ARGS, seed=0)
    sw = delay_sweep(*ARGS, "tail", 4, 2, 150, n_instances=2, n_draws=2, deltas=(0, 8), with_exact=False)
    insts = sweep_instances(*ARGS, 2)
    assert sw.deltas == (0, 4, 8)
    for gi, delta in enumerate(sw.deltas):
        idx = 0
        for k, inst in enumerate(insts):
            plain, buffered = plan_on_etas(inst), plan_on_etas(buffered_instance(inst, 2))
            for j in range(2):
                d = scenario_delays(inst, delta, "tail", draw_seed(k, j))
                expect = {
                    S: run_static(inst, d, plan=plain), P: run_static(inst, d, plan=buffered), N: run_reactive(inst, d, 1),
                    F: run_reactive(inst, d, forecast_hours(delta, 150)),
                }
                for key, ex in expect.items():
                    assert sw.values[key][gi][idx] == weighted_wait(inst, ex.starts, ex.arrivals), (delta, k, j, key)
                idx += 1


def test_unproven_exact_solutions_are_counted_and_get_the_sweep_time_limit(monkeypatch):
    import rb_evaluation
    from rb_exact import Clairvoyant
    limits = []

    def fake(inst, d, limit):
        limits.append(limit)
        return Clairvoyant({}, {}, 0.0, len(limits) % 2 == 0, "CP-SAT", 0.0)
    monkeypatch.setattr(rb_evaluation, "solve_clairvoyant", fake)
    sw = delay_sweep(*ARGS, "exp", 4, 1, 100, n_instances=2, n_draws=2, deltas=(4,), exact_time_limit=7)
    assert limits == [7] * 4 and sw.unproven == 2 and sw.values[X][0] == (0.0,) * 4
