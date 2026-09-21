"""Jedes Preset erzählt eine Geschichte (Abnahmekriterien aus dem Plan, Abschnitt 7, in rb_stories.py). Hier wird geprüft, dass sie trägt:

1. am gewählten Seed-Paar (sonst zeigt das Preset das Gegenteil dessen, was sein Hilfetext sagt),
2. im MITTEL der gewählten Flotte über 20 andere Verspätungs-Ziehungen, rauschstabil (Bootstrap): einzelne Ziehungen halten die Geschichte bewusst nicht
   immer, denn in jedem fünften Szenario verliert die Neuplanung - das ist der Kernbefund der Demo,
3. im MITTEL über viele Flotten (sonst ist das Preset ein Einzelfall, den man nach dem schönsten Seed ausgesucht hat), für Mittel UND Median,
4. dass Flotte und Ziehung typisch sind und keine Extremwerte.

Die Abstimmung selbst steht in tools/tune_presets.py, die Messwerte in tools/PRESET_SWEEP.md."""

import random
import statistics as st

import pytest

import rb_constants as C
from rb_delays import scenario_delays
from rb_evaluation import delay_sweep, distribution, run_strategies
from rb_presets import fleet_instance
from rb_stories import criteria, draw_holds, rel_of

S, P, N, F = C.STRAT_STARR, C.STRAT_PUFFER, C.STRAT_NEU, C.STRAT_PROGNOSE
NAMES = list(C.PRESETS)
DRAWS = range(20)
POP_INSTANCES, POP_DRAWS = 40, 3


def _fleet(name):
    p = C.PRESETS[name]
    return (p["n_ships"], p["quay_length"], p["arrival_spread"], p["handling_avg"], p["mainliner_pct"])


def _costs(name, fleet_seed=None, delay_seed=None):
    p = C.PRESETS[name]
    inst = fleet_instance(*_fleet(name), p["seed"] if fleet_seed is None else fleet_seed)
    d = scenario_delays(inst, p["delay_mean"], p["delay_kind"], p["delay_seed"] if delay_seed is None else delay_seed)
    return {o.key: o.wait_total for o in run_strategies(inst, d, p["delay_mean"], p["buffer"], p["forecast_pct"])}


_cache = {}


def _fleet_rows(name):
    if name not in _cache:
        _cache[("rows", name)] = [_costs(name, delay_seed=ds) for ds in DRAWS]
    return _cache[("rows", name)]


def _population(name):
    if ("pop", name) not in _cache:
        p = C.PRESETS[name]
        _cache[("pop", name)] = delay_sweep(*_fleet(name)[:4], p["mainliner_pct"] / 100, p["delay_kind"], p["delay_mean"], p["buffer"], p["forecast_pct"],
                                            n_instances=POP_INSTANCES, n_draws=POP_DRAWS, deltas=(p["delay_mean"],), with_exact=False)
    return _cache[("pop", name)]


def _pop_rel(sw):
    base = sw.mean(S, 0)
    return {k: 100 * (base - sw.mean(k, 0)) / base for k in (P, N, F)}


# ---------------- 1. am gewählten Seed-Paar ----------------
@pytest.mark.parametrize("name", NAMES)
def test_the_story_holds_in_the_single_draw_the_preset_shows(name):
    assert draw_holds(name, _costs(name)), (name, _costs(name))


@pytest.mark.parametrize("name", NAMES)
def test_the_shown_draw_is_typical_not_extreme(name):
    """Der gezeigte Gewinn der Neuplanung liegt zwischen dem 10. und 90. Perzentil der Ziehungen der Flotte (nicht der schönste Einzelfall)."""
    gains = sorted(r[S] - r[N] for r in _fleet_rows(name))
    shown = _costs(name)[S] - _costs(name)[N]
    assert gains[len(gains) // 10] <= shown <= gains[-len(gains) // 10 - 1], (name, shown, gains)


# ---------------- 2. rauschstabil: Mittel der Flotte über andere Ziehungen ----------------
@pytest.mark.parametrize("name", NAMES)
def test_the_story_holds_on_the_mean_of_the_preset_fleet_over_twenty_draws(name):
    for ok, text in criteria(name, rel_of(_fleet_rows(name))):
        assert ok, (name, text)


@pytest.mark.parametrize("name", NAMES)
def test_the_mean_statement_is_noise_stable_under_bootstrap(name):
    rows = _fleet_rows(name)
    rng = random.Random(4711)
    hits = sum(all(ok for ok, _ in criteria(name, rel_of([rows[rng.randrange(len(rows))] for _ in rows]))) for _ in range(300))
    assert hits / 300 >= 0.9, (name, hits / 300)


# ---------------- 3. im Mittel über die Grundgesamtheit ----------------
@pytest.mark.parametrize("name", NAMES)
def test_the_story_holds_on_average_over_many_fleets(name):
    for ok, text in criteria(name, _pop_rel(_population(name))):
        assert ok, (name, text)


def test_outliers_have_a_median_gain_far_below_the_mean():
    d = distribution(_population("Ausreißer"), N, C.PRESETS["Ausreißer"]["delay_mean"])
    assert d.median_gain <= 0.5 * d.mean_gain and d.top10_share > 0.4          # gemessen: Median 8 gegen Mittel 113, obere 10 % ≈ halber Gewinn


@pytest.mark.parametrize("name", ["Leichte Verspätung", "Große Verspätung", "Ausreißer", "Ruhiger Hafen"])
def test_gains_are_right_skewed_mean_above_median_and_some_scenarios_lose(name):
    d = distribution(_population(name), N, C.PRESETS[name]["delay_mean"])
    assert d.mean_gain > d.median_gain and d.worse > 0                          # der Mittelwert täuscht, und die Neuplanung verliert im Einzelfall


def test_large_delay_shows_the_forecast_adding_value_on_top_of_replanning():
    sw = _population("Große Verspätung")
    d_n, d_f = distribution(sw, N, 12), distribution(sw, F, 12)
    assert d_f.better > d_n.better and d_f.median_gain > d_n.median_gain and d_f.mean_gain > d_n.mean_gain


def test_punctual_preset_shows_the_buffer_cost_in_almost_every_scenario():
    d = distribution(_population("Pünktlich"), P, 0)
    assert d.worse >= 0.9 and d.better <= 0.05


def test_quiet_port_preset_lets_a_buffer_pay_and_replanning_still_beat_it():
    sw = _population("Ruhiger Hafen")
    rel = _pop_rel(sw)
    assert 0 < rel[P] < rel[N] < rel[F]


# ---------------- 4. typisch ----------------
@pytest.mark.parametrize("name", NAMES)
def test_the_preset_fleet_is_typical_for_its_population(name):
    """Der Gewinn der Neuplanung auf der gewählten Flotte liegt höchstens 12 Prozentpunkte neben dem der Grundgesamtheit."""
    fleet_rel = rel_of(_fleet_rows(name))
    assert abs(fleet_rel[N] - _pop_rel(_population(name))[N]) <= 12, (name, fleet_rel[N], _pop_rel(_population(name))[N])


def test_no_two_presets_share_the_same_fleet_and_delay_seed_pair_with_the_same_port_and_delay():
    keys = [tuple(sorted((k, v) for k, v in p.items())) for p in C.PRESETS.values()]
    assert len(set(keys)) == len(keys)


def test_presets_do_not_depend_on_the_delay_seed_when_there_is_no_delay():
    a, b = _costs("Pünktlich", delay_seed=0), _costs("Pünktlich", delay_seed=99)
    assert a == b
