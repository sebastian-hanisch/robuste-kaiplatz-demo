import itertools
import json

import pytest

import rb_constants as C
from helpers import manual_instance, ship
from rb_delays import scenario_delays
from rb_evaluation import (delay_sweep, distribution, run_strategies, SweepResult)
from rb_exact import solve_clairvoyant
from rb_scenario import make_instance
from rb_visualization import (berth_figure, comparison_figure, cost_curve_figure, distribution_figure, gain_figure, time_axis_end)

ARGS = (9, 600, 30, 14, 0.3)


def _scenario(delta=8, seed=3):
    inst = make_instance()
    d = scenario_delays(inst, delta, "exp", seed)
    return inst, d, run_strategies(inst, d, delta, 1, 100)


def _all_figures():
    inst, d, outs = _scenario()
    te = time_axis_end(inst, *[o.execution for o in outs])
    curve = delay_sweep(*ARGS, "exp", 8, 1, 100, n_instances=3, n_draws=2, deltas=(0, 8, 16))
    focus = delay_sweep(*ARGS, "exp", 8, 1, 100, n_instances=4, n_draws=2, deltas=(8,), with_exact=False)
    dists = [distribution(focus, k, 8) for k in (C.STRAT_PUFFER, C.STRAT_NEU, C.STRAT_PROGNOSE)]
    return [
        berth_figure(inst, outs[0].execution.plan, outs[0].execution.arrivals, "Starr", te),
        berth_figure(inst, outs[3].execution.plan, outs[3].execution.arrivals),
        cost_curve_figure(curve, 8, 3.2),
        distribution_figure(dists),
        gain_figure(dists),
        comparison_figure(outs),
    ]


def _lum(hexcolor):
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _colors(obj):
    """Alle Hex-Farben in Linien und Markerlinien und Textfarben der Spuren (was im dunklen Schema verschwinden könnte)."""
    found = []
    for trace in obj.data:
        for path in (("line", "color"), ("marker", "line", "color"), ("textfont", "color")):
            node = trace
            for part in path:
                node = getattr(node, part, None)
                if node is None:
                    break
            if isinstance(node, str) and node.startswith("#"):
                found.append(node)
    return found


# ---------- gemeinsame Konventionen ----------
@pytest.mark.parametrize("fig", _all_figures())
def test_every_figure_locks_axes_is_json_and_uses_white_template(fig):
    assert fig.layout.xaxis.fixedrange is True and fig.layout.yaxis.fixedrange is True         # Touch-Scrollen
    json.loads(fig.to_json())
    assert fig.layout.template.layout.plot_bgcolor == "white"


@pytest.mark.parametrize("fig", _all_figures())
def test_shapes_lie_below_the_traces_and_no_line_color_is_near_black(fig):
    assert all(s.layer == "below" for s in fig.layout.shapes if s.type == "rect")
    assert all(_lum(c) > 0.2 for c in _colors(fig)), _colors(fig)                            # im dunklen Schema sonst unsichtbar


# ---------- Kai-Diagramm ----------
def _rects(fig):
    return [s for s in fig.layout.shapes if s.type == "rect"]


def _trace(fig, name):
    return next(t for t in fig.data if t.name == name)


def test_berth_figure_draws_each_ship_at_its_executed_position_and_size():
    inst, d, outs = _scenario()
    ex = outs[2].execution
    fig = berth_figure(inst, ex.plan, ex.arrivals)
    zones = [s for s in _rects(fig) if s.x0 == 0 and s.x1 == fig.layout.xaxis.range[1] and (s.y0, s.y1) in [(z.start, z.end) for z in inst.zones]]
    boxes = [s for s in _rects(fig) if s not in zones]
    assert len(zones) == len(inst.zones) and len(boxes) == len(inst.ships)
    expected = {(ex.starts[s.index], ex.starts[s.index] + s.handling_time, ex.positions[s.index], ex.positions[s.index] + s.length) for s in inst.ships}
    assert {(b.x0, b.x1, b.y0, b.y1) for b in boxes} == expected


def test_berth_figure_boxes_of_a_feasible_plan_never_overlap():
    inst, d, outs = _scenario()
    for o in outs:
        fig = berth_figure(inst, o.execution.plan, o.execution.arrivals)
        boxes = [s for s in _rects(fig) if s.fillcolor in C.PRIORITY_COLORS.values()]
        assert len(boxes) == len(inst.ships)
        for a, b in itertools.combinations(boxes, 2):
            ox = min(a.x1, b.x1) - max(a.x0, b.x0)
            oy = min(a.y1, b.y1) - max(a.y0, b.y0)
            assert not (ox > 1e-9 and oy > 1e-9)


def test_berth_figure_marks_actual_arrival_for_every_ship_and_eta_only_for_delayed_ships():
    inst, d, outs = _scenario()
    ex = outs[0].execution
    fig = berth_figure(inst, ex.plan, ex.arrivals)
    arr = _trace(fig, "tatsächliche Ankunft ◆")
    eta = _trace(fig, "Fahrplan-Ankunft ▽")
    centers = {s.index: ex.positions[s.index] + s.length / 2 for s in inst.ships}
    assert sorted(zip(arr.x, arr.y)) == sorted((ex.arrivals[i], centers[i]) for i in centers)
    late = [s for s in inst.ships if ex.arrivals[s.index] > s.arrival]
    assert late and len(late) < len(inst.ships)
    assert sorted(zip(eta.x, eta.y)) == sorted((s.arrival, centers[s.index]) for s in late)


def test_berth_figure_delay_and_wait_lines_run_from_eta_to_arrival_and_from_arrival_to_start():
    inst, d, outs = _scenario()
    ex = outs[0].execution
    fig = berth_figure(inst, ex.plan, ex.arrivals)

    def segments(trace):
        xs, ys, segs, cur = list(trace.x), list(trace.y), [], []
        for x, y in zip(xs, ys):
            if x is None:
                segs.append(cur)
                cur = []
            else:
                cur.append((x, y))
        return segs

    delay = segments(_trace(fig, "Verspätung"))
    wait = segments(_trace(fig, "Wartezeit"))
    exp_delay = sorted(((s.arrival, ex.positions[s.index] + s.length / 2), (ex.arrivals[s.index], ex.positions[s.index] + s.length / 2))
                       for s in inst.ships if ex.arrivals[s.index] > s.arrival)
    exp_wait = sorted(((ex.arrivals[s.index], ex.positions[s.index] + s.length / 2), (ex.starts[s.index], ex.positions[s.index] + s.length / 2))
                      for s in inst.ships if ex.starts[s.index] > ex.arrivals[s.index])
    assert sorted(tuple(x) for x in delay) == [tuple(x) for x in exp_delay]
    assert sorted(tuple(x) for x in wait) == [tuple(x) for x in exp_wait]


def test_berth_figure_without_delay_and_waiting_has_no_lines_and_no_eta_markers():
    inst = manual_instance([ship(0, 40, 0, 10), ship(1, 40, 0, 10)], quay_length=100)
    fig = berth_figure(inst, {0: (0, 0), 1: (0, 50)}, {0: 0, 1: 0})
    assert len(_trace(fig, "Verspätung").x) == 0 and len(_trace(fig, "Wartezeit").x) == 0 and len(_trace(fig, "Fahrplan-Ankunft ▽").x) == 0
    assert len(_trace(fig, "tatsächliche Ankunft ◆").x) == 2


def test_berth_figure_hover_covers_the_whole_box_and_names_the_ship():
    inst, d, outs = _scenario()
    ex = outs[2].execution
    fig = berth_figure(inst, ex.plan, ex.arrivals)
    hover = _trace(fig, "Schiffe")
    assert hover.marker.opacity == 0 and hover.hovertemplate == "%{text}<extra></extra>"
    for s in inst.ships:
        pts = [(x, y, t) for x, y, t in zip(hover.x, hover.y, hover.text) if f"<b>{s.name}</b>" in t]
        assert len(pts) >= 9
        x0, y0 = ex.starts[s.index], ex.positions[s.index]
        assert all(x0 < x < x0 + s.handling_time and y0 < y < y0 + s.length for x, y, _ in pts)
        assert f"Wartezeit: {ex.starts[s.index] - ex.arrivals[s.index]} h" in pts[0][2]
        assert f"Verspätung {ex.arrivals[s.index] - s.arrival} h" in pts[0][2]


def test_berth_figure_numbers_the_ships_from_one_and_shows_priority_legend_only_for_present_classes():
    inst, d, outs = _scenario()
    ex = outs[0].execution
    fig = berth_figure(inst, ex.plan, ex.arrivals)
    nums = _trace(fig, "Schiffsnummern")
    assert sorted(nums.text, key=int) == [str(i + 1) for i in range(len(inst.ships))]
    legend = {t.name for t in fig.data if t.name in C.PRIORITIES}
    assert legend == {s.priority for s in inst.ships}
    only_tramp = manual_instance([ship(0, 40, 0, 10)])
    f2 = berth_figure(only_tramp, {0: (0, 0)}, {0: 0})
    assert {t.name for t in f2.data if t.name in C.PRIORITIES} == {"Tramp"}


def test_berth_figure_axes_cover_the_quay_and_the_time_range_is_shared_when_given():
    inst, d, outs = _scenario()
    te = time_axis_end(inst, *[o.execution for o in outs])
    for o in outs:
        fig = berth_figure(inst, o.execution.plan, o.execution.arrivals, t_end=te)
        assert tuple(fig.layout.xaxis.range) == (0, te) and tuple(fig.layout.yaxis.range) == (0, inst.quay_length)
    assert te % 24 == 0
    for o in outs:
        for s in inst.ships:
            assert o.execution.starts[s.index] + s.handling_time <= te and o.execution.arrivals[s.index] <= te


def test_time_axis_end_rounds_up_to_whole_days_and_uses_arrivals_and_all_runs():
    class Run:
        def __init__(self, plan, arrivals):
            self.plan, self.arrivals = plan, arrivals
    inst = manual_instance([ship(0, 40, 0, 10), ship(1, 40, 0, 10)])
    assert time_axis_end(inst, Run({0: (0, 0), 1: (0, 50)}, {0: 0, 1: 0})) == 24
    assert time_axis_end(inst, Run({0: (14, 0), 1: (0, 50)}, {0: 0, 1: 0})) == 24              # Ende genau 24: bleibt 24
    assert time_axis_end(inst, Run({0: (15, 0), 1: (0, 50)}, {0: 0, 1: 0})) == 48
    assert time_axis_end(inst, Run({0: (0, 0), 1: (0, 50)}, {0: 0, 1: 30})) == 48              # späte Ankunft zählt
    assert time_axis_end(inst, Run({0: (0, 0), 1: (0, 50)}, {0: 0, 1: 0}), Run({0: (40, 0), 1: (0, 50)}, {0: 0, 1: 0})) == 72
    assert time_axis_end(inst) == 24


def test_berth_figure_title_is_optional():
    inst, d, outs = _scenario()
    ex = outs[0].execution
    assert berth_figure(inst, ex.plan, ex.arrivals, "Mein Titel").layout.title.text == "Mein Titel"
    assert not berth_figure(inst, ex.plan, ex.arrivals).layout.title.text


def test_berth_figure_also_draws_the_clairvoyant_plan():
    inst, d, outs = _scenario()
    ex = solve_clairvoyant(inst, d)
    fig = berth_figure(inst, ex.plan, {i: inst.ships[i].arrival + d[i] for i in d})
    assert len([s for s in _rects(fig) if s.fillcolor in C.PRIORITY_COLORS.values()]) == len(inst.ships)


# ---------- Kostenkurve ----------
def test_cost_curve_has_band_and_line_per_strategy_with_the_sweep_values():
    curve = delay_sweep(*ARGS, "exp", 8, 1, 100, n_instances=3, n_draws=2, deltas=(0, 8, 16))
    fig = cost_curve_figure(curve, 8, None)
    lines = {t.name: t for t in fig.data if t.mode == "lines+markers"}
    assert set(lines) == set(C.STRATEGY_LABELS.values())
    assert len(fig.data) == 2 * len(C.STRATEGY_KEYS)
    for key in C.STRATEGY_KEYS:
        t = lines[C.STRATEGY_LABELS[key]]
        assert list(t.x) == [0, 8, 16]
        assert list(t.y) == pytest.approx([curve.mean(key, i) for i in range(3)])
        assert t.line.color == C.STRATEGY_COLORS[key] and t.line.dash == C.STRATEGY_DASH.get(key, "solid")
    band = next(t for t in fig.data if t.name == "⏱️ Starrer Plan (Band)")
    ys = list(band.y)
    n = 3
    assert ys[:n] == pytest.approx([curve.mean(C.STRAT_STARR, i) + curve.sem(C.STRAT_STARR, i) for i in range(n)])
    assert ys[n:] == pytest.approx([curve.mean(C.STRAT_STARR, i) - curve.sem(C.STRAT_STARR, i) for i in range(n - 1, -1, -1)])


def test_cost_curve_marks_the_set_delay_and_the_tipping_point_only_inside_the_range():
    curve = delay_sweep(*ARGS, "exp", 8, 1, 100, n_instances=2, n_draws=1, deltas=(0, 16), with_exact=False)
    xs = lambda fig: sorted(s.x0 for s in fig.layout.shapes if s.type == "line")
    assert xs(cost_curve_figure(curve, 8, None)) == [8]
    assert xs(cost_curve_figure(curve, 8, 3.2)) == [3.2, 8]
    assert xs(cost_curve_figure(curve, 8, 0.0)) == [8]                                   # 0 = "schon ohne Verspätung": keine Linie
    assert xs(cost_curve_figure(curve, 8, 20)) == [8]                                    # jenseits des Rasters


def test_cost_curve_without_exact_omits_that_strategy():
    curve = delay_sweep(*ARGS, "exp", 8, 1, 100, n_instances=2, n_draws=1, deltas=(0, 16), with_exact=False)
    fig = cost_curve_figure(curve, 8)
    assert C.STRATEGY_LABELS[C.STRAT_EXACT] not in {t.name for t in fig.data}
    assert len(fig.data) == 2 * (len(C.STRATEGY_KEYS) - 1)
    assert fig.layout.yaxis.rangemode == "tozero"


# ---------- Verteilung und Gewinne ----------
def _fake_sweep(series, n_ships=1):
    n = len(next(iter(series.values()))[0])
    return SweepResult((8,), "exp", n_ships, n, {k: tuple(tuple(v) for v in vs) for k, vs in series.items()}, 0)


def test_distribution_figure_bars_are_the_shares_in_percent_and_sum_to_100():
    base = [100] * 10
    gains = [10, 10, 10, 10, 0, 0, 0, -5, -5, -5]
    sw = _fake_sweep({C.STRAT_STARR: [base], C.STRAT_NEU: [[b - g for b, g in zip(base, gains)]]})
    fig = distribution_figure([distribution(sw, C.STRAT_NEU, 8)])
    by = {t.name: t for t in fig.data}
    assert list(by["besser als starr"].x) == [40] and list(by["gleich"].x) == [30] and list(by["schlechter als starr"].x) == [30]
    assert sum(t.x[0] for t in fig.data) == pytest.approx(100)
    assert by["besser als starr"].marker.color == C.OUTCOME_COLORS["better"] and by["schlechter als starr"].marker.color == C.OUTCOME_COLORS["worse"]
    assert list(by["besser als starr"].text) == ["40 %"]
    assert list(fig.data[0].y) == ["Neuplanung"] and fig.layout.legend.traceorder == "normal"


def test_distribution_figure_hides_labels_of_slivers():
    sw = _fake_sweep({C.STRAT_STARR: [[100] * 20], C.STRAT_NEU: [[100] * 19 + [90]]})
    fig = distribution_figure([distribution(sw, C.STRAT_NEU, 8)])
    by = {t.name: t for t in fig.data}
    assert list(by["besser als starr"].text) == [""] and list(by["gleich"].text) == ["95 %"]


def test_gain_figure_shows_median_next_to_mean():
    base = [100] * 10
    gains = [0] * 8 + [1, 100]
    sw = _fake_sweep({C.STRAT_STARR: [base], C.STRAT_PROGNOSE: [[b - g for b, g in zip(base, gains)]]})
    d = distribution(sw, C.STRAT_PROGNOSE, 8)
    fig = gain_figure([d])
    by = {t.name: t for t in fig.data}
    assert list(by["Median (typisches Szenario)"].y) == [0] and list(by["Mittelwert"].y) == [pytest.approx(10.1)]
    assert list(by["Mittelwert"].x) == ["Neuplanung<br>+ Prognose"]


# ---------- Vergleich ----------
def test_comparison_figure_uses_the_outcome_numbers():
    inst, d, outs = _scenario()
    fig = comparison_figure(outs)
    totals = fig.data[0]
    assert list(totals.y) == [o.wait_total for o in outs]
    assert list(totals.marker.color) == [C.STRATEGY_COLORS[o.key] for o in outs]
    per_class = {t.name: t for t in fig.data[1:]}
    assert set(per_class) == {o.label for o in outs}
    for o in outs:
        assert list(per_class[o.label].x) == list(C.PRIORITIES)
        assert list(per_class[o.label].y) == [o.wait_by_priority.get(p, 0.0) for p in C.PRIORITIES]


def test_hover_points_form_a_full_grid_inside_the_box():
    from rb_visualization import _hover_points
    xs, ys = _hover_points(10, 20, 100, 130)
    assert len(xs) == len(ys) == 15
    assert len(set(zip(xs, ys))) == 15 and len(set(xs)) == 5 and len(set(ys)) == 3
    assert xs[:5] == [11.0, 13.0, 15.0, 17.0, 19.0] and ys[::5] == [105.0, 115.0, 125.0]


def test_default_time_range_is_the_needed_range_and_covers_everything():
    inst, d, outs = _scenario(delta=16)
    ex = outs[0].execution
    fig = berth_figure(inst, ex.plan, ex.arrivals)
    assert fig.layout.xaxis.range[1] == time_axis_end(inst, ex) and fig.layout.xaxis.range[1] > 24
    assert all(s.x1 <= fig.layout.xaxis.range[1] for s in fig.layout.shapes if s.type == "rect")


def test_tipping_line_is_drawn_exactly_at_the_end_of_the_grid():
    curve = delay_sweep(*ARGS, "exp", 8, 1, 100, n_instances=2, n_draws=1, deltas=(0, 16), with_exact=False)
    xs = lambda fig: sorted(s.x0 for s in fig.layout.shapes if s.type == "line")
    assert xs(cost_curve_figure(curve, 8, 16)) == [8, 16]


def test_distribution_labels_appear_from_six_percent_and_the_axis_ends_at_100():
    base = [100] * 50
    sw = _fake_sweep({C.STRAT_STARR: [base], C.STRAT_NEU: [[100 - 10] * 3 + [100] * 47]})              # 3 von 50 = 6 % besser
    fig = distribution_figure([distribution(sw, C.STRAT_NEU, 8)])
    by = {t.name: t for t in fig.data}
    assert by["besser als starr"].x[0] == pytest.approx(6.0) and list(by["besser als starr"].text) == ["6 %"]
    assert tuple(fig.layout.xaxis.range) == (0, 100)
