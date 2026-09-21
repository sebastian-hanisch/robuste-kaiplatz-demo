"""Panel-Test über Streamlits AppTest: rendert alle Strategie-Panels und den Exakt-Tab in einem Skript (fängt doppelte Widget-IDs)."""

import json

from streamlit.testing.v1 import AppTest

from rb_delays import actual_arrivals, scenario_delays
from rb_evaluation import run_strategies
from rb_exact import price_of_uncertainty, solve_clairvoyant
from rb_scenario import make_instance
from rb_visualization import time_axis_end


def _script_strategies():
    import streamlit as st

    from rb_delays import scenario_delays
    from rb_evaluation import run_strategies
    from rb_scenario import make_instance
    from rb_ui_panel import render_strategy_panel
    from rb_visualization import time_axis_end

    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 3)
    outs = run_strategies(inst, d, 8, 1, 100)
    te = time_axis_end(inst, *[o.execution for o in outs])
    tabs = st.tabs([o.label for o in outs])
    for tab, o in zip(tabs, outs):
        with tab:
            render_strategy_panel(f"strategy_{o.key}", o, outs, inst, te)


def _script_exact(proven, source):
    from rb_delays import actual_arrivals, scenario_delays
    from rb_evaluation import run_strategies
    from rb_exact import Clairvoyant, solve_clairvoyant
    from rb_scenario import make_instance
    from rb_ui_panel import render_exact_panel
    from rb_visualization import time_axis_end

    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 3)
    outs = run_strategies(inst, d, 8, 1, 100)
    ex = solve_clairvoyant(inst, d)
    ex = Clairvoyant(ex.starts, ex.positions, ex.weighted_wait, proven, source, 42.0)
    te = time_axis_end(inst, *[o.execution for o in outs])
    render_exact_panel("exact", inst, ex, outs, actual_arrivals(inst, d), te)


def _color(metric):
    enum = metric.proto.DESCRIPTOR.fields_by_name["color"].enum_type
    return enum.values_by_number[metric.proto.color].name


def _run(fn, *args):
    at = AppTest.from_function(fn, args=args)
    at.run(timeout=120)
    return at


def _num(text):
    return float(text.replace("−", "-").split()[0])


# ---------------- Strategie-Panels ----------------
def test_all_four_strategy_panels_render_without_exception():
    at = _run(_script_strategies)
    assert not at.exception, [str(e) for e in at.exception]
    assert len(at.tabs) == 4
    assert len(at.metric) == 16                                       # 4 Kennzahlen je Panel
    assert len(at.caption) == 4                                       # Verschiebung des angekündigten Anlegebeginns


def test_metric_labels_and_counters():
    at = _run(_script_strategies)
    tabs = [list(t.metric) for t in at.tabs]
    for metrics in tabs:
        assert [m.label for m in metrics] == ["Wartezeit gewichtet", "je Schiff", "Neuplanungen", "Positionswechsel"]
    starr, puffer, neu, prognose = tabs
    assert int(starr[2].value) == 0 and int(starr[3].value) == 0 and int(puffer[2].value) == 0       # nie neu geplant
    assert int(neu[2].value) >= 1 and int(prognose[2].value) >= 1


def test_reference_panel_has_no_deltas_and_the_others_show_mine_minus_reference():
    at = _run(_script_strategies)
    tabs = [list(t.metric) for t in at.tabs]
    assert tabs[0][0].delta in (None, "") and tabs[0][1].delta in (None, "")
    ref_total, ref_ship = _num(tabs[0][0].value), _num(tabs[0][1].value)
    for metrics in tabs[1:]:
        assert abs(_num(metrics[0].delta) - (_num(metrics[0].value) - ref_total)) <= 1.0            # gerundet angezeigt
        assert abs(_num(metrics[1].delta) - (_num(metrics[1].value) - ref_ship)) <= 0.15


def test_delta_colors_are_inverted_less_waiting_is_green():
    at = _run(_script_strategies)
    seen = set()
    for t in list(at.tabs)[1:]:
        m = t.metric[0]
        d = _num(m.delta)
        if d != 0:
            assert _color(m) == ("GREEN" if d < 0 else "RED")
            seen.add(_color(m))
    assert seen                                                    # mindestens ein Fall geprüft


def test_each_strategy_panel_shows_its_own_description_and_chart():
    at = _run(_script_strategies)
    texts = [" ".join(m.value for m in t.markdown) for t in at.tabs]
    assert "Starrer Plan" in texts[0] and "Puffer" in texts[1] and "Neuplanung." in texts[2] and "Prognose" in texts[3]
    assert not at.exception


# ---------------- Exakt-Tab ----------------
def test_exact_panel_proven_shows_caption_and_price_of_uncertainty_for_every_strategy():
    at = _run(_script_exact, True, "CP-SAT")
    assert not at.exception, [str(e) for e in at.exception]
    assert len(at.warning) == 0
    assert any("Bewiesen optimal" in c.value and "42 ms" in c.value for c in at.caption)
    assert len(at.metric) == 5 and at.metric[0].label == "Hellsehen: gewichtete Wartezeit"
    assert "nicht bewiesen" not in at.metric[0].value
    assert all(_num(m.value) >= 0 for m in list(at.metric)[1:])


def test_exact_panel_flags_a_result_without_proof():
    at = _run(_script_exact, False, "CP-SAT")
    assert not at.exception
    assert len(at.warning) == 1 and "nicht bewiesen" in at.warning[0].value and "Zeitlimit" in at.warning[0].value
    assert "(nicht bewiesen)" in at.metric[0].value


def test_exact_panel_flags_the_heuristic_fallback():
    at = _run(_script_exact, False, "Heuristik")
    assert not at.exception
    assert len(at.warning) == 1 and "keine Lösung" in at.warning[0].value and "Heuristik" in at.warning[0].value
    assert "(nicht bewiesen)" in at.metric[0].value


# ---------------- Werte gegen eine unabhängige Rechnung derselben Szenarien ----------------
def _scenario():
    inst = make_instance()
    d = scenario_delays(inst, 8, "exp", 3)
    return inst, d, run_strategies(inst, d, 8, 1, 100)


def test_strategy_panel_numbers_are_the_outcome_numbers():
    inst, d, outs = _scenario()
    at = _run(_script_strategies)
    for tab, o in zip(at.tabs, outs):
        m = list(tab.metric)
        assert m[0].value == f"{o.wait_total:.0f} h" and m[1].value == f"{o.wait_per_ship:.1f} h"
        assert int(m[2].value) == o.replans and int(m[3].value) == o.position_changes
        assert f"{o.window_shift:.1f} h" in tab.caption[0].value


def test_per_ship_delta_uses_the_inverted_color_too():
    at = _run(_script_strategies)
    checked = 0
    for t in list(at.tabs)[1:]:
        m = t.metric[1]
        d = _num(m.delta)
        if d != 0:
            assert _color(m) == ("GREEN" if d < 0 else "RED")
            checked += 1
    assert checked


def test_all_charts_share_the_time_axis_of_the_scenario():
    inst, d, outs = _scenario()
    te = time_axis_end(inst, *[o.execution for o in outs])
    assert any(time_axis_end(inst, o.execution) != te for o in outs)              # sonst wäre der Test wirkungslos
    at = _run(_script_strategies)
    charts = at.get("plotly_chart")
    assert len(charts) == 4
    for c in charts:
        assert json.loads(c.proto.spec)["layout"]["xaxis"]["range"] == [0, te]


def test_exact_panel_numbers_and_shared_time_axis():
    inst, d, outs = _scenario()
    ex = solve_clairvoyant(inst, d)
    at = _run(_script_exact, True, "CP-SAT")
    assert at.metric[0].value == f"{ex.weighted_wait:.0f} h"
    for m, o in zip(list(at.metric)[1:], outs):
        assert m.label == o.label and m.value == f"{price_of_uncertainty(o.wait_total, ex):.0f} h"
    te = time_axis_end(inst, *[o.execution for o in outs])
    spec = json.loads(at.get("plotly_chart")[0].proto.spec)
    assert spec["layout"]["xaxis"]["range"] == [0, te]
