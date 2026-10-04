"""End-to-end-Tests der Streamlit-App über AppTest. Stichproben werden klein gemacht (Konstanten), damit die Läufe schnell bleiben;
die Aussagen über die echten Stichproben stehen in test_preset_stories.py."""

import json
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import rb_constants as C
import rb_presets as P
from rb_scenario import is_playable

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
FOOTER = (
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). "
    "Mehr zum Thema: [Hafenlogistik optimieren](https://sebastianhanisch.net/hafenlogistik-optimierung.html)."
)


@pytest.fixture(scope="module", autouse=True)
def small_samples():
    mp = pytest.MonkeyPatch()
    mp.setattr(C, "FOCUS_INSTANCES", 4)
    mp.setattr(C, "FOCUS_DRAWS", 2)
    mp.setattr(C, "SWEEP_INSTANCES", 3)
    mp.setattr(C, "SWEEP_DRAWS", 1)
    mp.setattr(C, "SWEEP_DELTAS", (0, 8, 16))
    yield
    mp.undo()


def _at(**state):
    at = AppTest.from_file(APP, default_timeout=240)
    for key, value in state.items():
        at.session_state[key] = value
    return at


def _run(**state):
    at = _at(**state)
    at.run()
    assert not at.exception, [str(e) for e in at.exception]
    return at


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def _texts(elements):
    return [e.value for e in elements]


def _state_of(at):
    return {k: at.session_state[k] for k in P.SETTING_SPECS}


# ---------------- Skelett ----------------
def test_skeleton_title_presets_sidebar_expanders_and_verbatim_footer():
    at = _run()
    assert at.title[0].value == "🚢 Robuste Kaiplatzplanung: Puffer oder Information?"
    assert [b.label for b in at.button][:5] == list(C.PRESETS)                        # Presets im Hauptbereich, zuerst
    assert len(at.sidebar.header) == 1 and at.sidebar.header[0].value == "⚙️ Einstellungen"
    assert not at.main.header and not at.sidebar.subheader                            # kein zweiter Header in der Seitenleiste
    assert [e.label for e in at.expander] == ["🔧 Wie wir das erreichen – vollständiger Methodenvergleich", "Wie funktioniert diese Demo?",
                                              "📐 Mathematische Formulierung"]
    assert at.caption[-1].value == FOOTER
    assert any("Puffer oder Information?" in s.value for s in at.subheader)
    assert any(m.value.startswith("## 🎯") for m in at.markdown)


def test_sidebar_widgets_use_the_bounds_of_the_presets_module_and_keep_the_documented_order():
    at = _run()
    labels = [w.label for w in list(at.sidebar.slider) + list(at.sidebar.number_input) + list(at.sidebar.radio)]
    assert labels == ["Anzahl Schiffe", "Kailänge (m)", "Ankunftsfenster (h)", "Ø Liegezeit (h)", "Anteil Mainliner (%)", "Mittlere Verspätung (h)",
                      "Puffer (h)", "Prognose (% der mittleren Verspätung)", "Seed der Schiffe", "Seed der Verspätungen", "Verspätungsart"]
    for key in P.SETTING_SPECS:
        widgets = [w for w in list(at.slider) + list(at.number_input) if w.key == key]
        if widgets:
            assert (widgets[0].min, widgets[0].max) == tuple(float(x) for x in P.bounds(key)) or (widgets[0].min, widgets[0].max) == P.bounds(key)
    assert [b.label for b in at.sidebar.button] == ["🎲 Neue Schiffe", "🎲 Neue Verspätungen"]


def test_main_view_shows_four_strategy_metrics_with_deltas_relative_to_the_static_plan():
    at = _run()
    metrics = [m for m in at.main.metric][:4]
    assert [m.label for m in metrics] == list(C.STRATEGY_LABELS.values())[:4]
    assert metrics[0].delta in (None, "")                                              # die Referenz hat kein Delta
    ref = float(metrics[0].value.split()[0])
    for m in metrics[1:]:
        value = float(m.value.split()[0])
        delta = float(m.delta.replace("−", "-").split()[0])
        assert delta == pytest.approx(value - ref, abs=0.11)                           # mine minus Referenz (gerundet angezeigt)
    info = [i.value for i in at.info if "eine** Ziehung" in i.value]
    assert len(info) == 1 and "Seed 3" in info[0]


def test_zero_delta_is_shown_neutral_not_as_a_red_increase():
    at = _run(delay_mean_slider=0)
    metrics = [m for m in at.main.metric][:4]
    same = [m for m in metrics[1:] if m.delta == "0.0 h"]
    assert same, "ohne Verspätung sind mehrere Strategien gleich gut wie starr"
    for m in same:
        enum = m.proto.DESCRIPTOR.fields_by_name["color"].enum_type
        assert enum.values_by_number[m.proto.color].name == "GRAY"


def test_kai_view_has_two_charts_with_a_shared_time_axis_and_the_radio_switches_the_right_side():
    at = _run()
    charts = [json.loads(c.proto.spec) for c in at.get("plotly_chart")][:2]
    assert charts[0]["layout"]["xaxis"]["range"] == charts[1]["layout"]["xaxis"]["range"]
    heads = [m.value for m in at.markdown if m.value.startswith("**") and m.value.endswith("**")]
    assert "**⏱️ Starrer Plan**" in heads and "**🔮 Neuplanung + Prognose**" in heads        # Überschriften stehen über den Diagrammen, nicht im Diagramm
    radio = at.radio(key="kai_view_radio")
    assert radio.options == [C.STRATEGY_LABELS[k] for k in (C.STRAT_PUFFER, C.STRAT_NEU, C.STRAT_PROGNOSE)] and radio.index == 2
    radio.set_value(C.STRAT_PUFFER).run()
    assert not at.exception
    assert "**🧱 Puffer**" in [m.value for m in at.markdown] and "**🔮 Neuplanung + Prognose**" not in [m.value for m in at.markdown]


# ---------------- Kernabschnitt ----------------
def test_core_section_shows_three_gain_metrics_three_verdicts_and_the_distribution_charts():
    at = _run()
    gains = [m for m in at.main.metric if m.label in ("Puffer", "Neuplanung", "+ Prognose")]
    assert [m.label for m in gains] == ["Puffer", "Neuplanung", "+ Prognose"]
    assert any(m.value.startswith("**Gewinn gegen den starren Plan**") for m in at.markdown)      # gemeinsame Überschrift statt langer Kennzahlen-Namen
    boxes = list(at.success) + list(at.warning) + list(at.info)
    verdicts = [b for b in boxes if any(w in b.value for w in ("lohnt sich hier", "kostet hier mehr", "Kein klarer Unterschied"))]
    assert len(verdicts) == 3
    keys = {c.proto.id for c in at.get("plotly_chart")}
    assert len(at.get("plotly_chart")) == 9 and len(keys) == 9                          # 2 Kai + 2 Kernabschnitt + 4 Strategie-Panels + Vergleich, keine doppelten IDs


def test_each_verdict_is_exactly_one_of_the_three_states_and_mentions_the_loss_share():
    at = _run(delay_mean_slider=12)
    verdicts = [b for b in list(at.success) + list(at.warning) + list(at.info)
                if any(w in b.value for w in ("lohnt sich hier", "kostet hier mehr", "Kein klarer Unterschied"))]
    assert len(verdicts) == 3
    assert all("Einzelne Szenarien weichen ab" in v.value and "Median-Gewinn" in v.value for v in verdicts)


def test_curve_is_not_computed_until_the_button_is_clicked_and_then_shows_metrics_and_chart():
    at = _run()
    pending = lambda: sum("Noch nichts berechnet" in i.value for i in at.info)
    assert pending() == 2                                                             # Kurve und Exakt-Tab warten auf ihren Knopf
    assert not [m for m in at.main.metric if m.label.startswith("Puffer lohnt ab")]
    _button(at, "📈 Kostenkurve berechnen").click().run()
    assert not at.exception, [str(e) for e in at.exception]
    labels = [m.label for m in at.main.metric]
    assert "Puffer-Aufpreis" in labels and "Puffer lohnt ab" in labels and "Unsicherheitspreis" in labels
    specs = [json.loads(c.proto.spec) for c in at.get("plotly_chart")]
    assert any(len(s["data"]) >= 10 and s["layout"]["xaxis"]["title"]["text"].startswith("mittlere Verspätung") for s in specs)
    assert pending() == 1                                                             # nur der Exakt-Tab wartet noch


def test_curve_stays_valid_when_only_the_delay_or_a_seed_changes_but_goes_stale_when_the_port_or_strategy_changes():
    at = _run()
    _button(at, "📈 Kostenkurve berechnen").click().run()
    assert not at.exception
    at.slider(key="delay_mean_slider").set_value(4).run()
    assert not any("zuletzt berechnete Kurve" in i.value for i in at.info) and any(m.label == "Puffer lohnt ab" for m in at.main.metric)
    at.number_input(key="delay_seed_input").set_value(11).run()
    assert not any("zuletzt berechnete Kurve" in i.value for i in at.info)
    at.slider(key="buffer_slider").set_value(3).run()
    assert any("zuletzt berechnete Kurve" in i.value for i in at.info) and not any(m.label == "Puffer lohnt ab" for m in at.main.metric)


# ---------------- Methodenvergleich ----------------
def test_comparison_expander_has_a_tab_per_strategy_plus_exact_and_comparison_and_no_duplicate_ids():
    at = _run()
    labels = [t.label for t in at.tabs]
    assert labels[-2:] == ["🧮 Exakt (Hellsehen)", "📊 Vergleich"] and labels[:4] == list(C.STRATEGY_LABELS.values())[:4]
    assert len(at.get("plotly_chart")) == 4 + 4 + 1                                     # Kernabschnitt + 4 Panels + Vergleich
    assert len({c.proto.id for c in at.get("plotly_chart")}) == len(at.get("plotly_chart"))


def test_exact_tab_computes_on_click_marks_the_result_and_goes_stale_on_a_scenario_change():
    at = _run()
    assert any("Noch nichts berechnet" in i.value for i in at.info)
    _button(at, "🧮 Hellsehen berechnen").click().run()
    assert not at.exception, [str(e) for e in at.exception]
    assert any(m.label == "Hellsehen: gewichtete Wartezeit" for m in at.metric)
    assert any("Bewiesen optimal" in c.value for c in at.caption)
    table = at.dataframe[-1].value
    assert any("Hellsehen" in str(v) for v in table["Strategie"])                       # Vergleichstabelle bekommt die Hellsehen-Zeile
    at.slider(key="delay_mean_slider").set_value(3).run()
    assert not at.exception
    assert any("bezog sich auf ein anderes Szenario" in i.value for i in at.info)
    assert not any(m.label == "Hellsehen: gewichtete Wartezeit" for m in at.metric)


def test_exact_result_does_not_change_when_only_the_strategy_settings_change():
    at = _run()
    _button(at, "🧮 Hellsehen berechnen").click().run()
    at.slider(key="buffer_slider").set_value(5).run()
    assert not at.exception and any(m.label == "Hellsehen: gewichtete Wartezeit" for m in at.metric)


def test_comparison_table_lists_the_four_strategies_with_deltas_to_the_static_plan():
    at = _run()
    table = at.dataframe[0].value
    assert list(table["Strategie"]) == list(C.STRATEGY_LABELS.values())[:4]
    col = [c for c in table.columns if c.startswith("Differenz zu")][0]
    assert table[col].iloc[0] == 0 and {"Neuplanungen", "Positionswechsel"} <= set(table.columns)


# ---------------- Presets und Permalink ----------------
@pytest.mark.parametrize("name", list(C.PRESETS))
def test_every_preset_loads_without_exception_and_sets_all_widgets(name):
    at = _run()
    _button(at, name).click().run()
    assert not at.exception, [str(e) for e in at.exception]
    for field, key in P.PRESET_STATE_KEYS.items():
        assert at.session_state[key] == C.PRESETS[name][field], (name, key)


def test_permalink_loads_clamps_snaps_and_ignores_garbage():
    at = _at()
    at.query_params["dm"] = "999"
    at.query_params["fc"] = "47"
    at.query_params["dk"] = "tail"
    at.query_params["ns"] = "abc"
    at.run()
    assert not at.exception
    assert at.session_state["delay_mean_slider"] == 16 and at.session_state["forecast_slider"] == 50
    assert at.session_state["delay_kind_radio"] == "tail" and at.session_state["n_ships_slider"] == C.N_SHIPS_DEFAULT


def test_the_address_bar_mirrors_every_setting_after_a_run():
    at = _run()
    for key, spec in P.SETTING_SPECS.items():
        assert at.query_params[spec.url_param] == [spec.encoder(at.session_state[key])] or at.query_params[spec.url_param] == spec.encoder(at.session_state[key])


def test_permalink_round_trip_reproduces_the_scenario():
    first = _run(delay_mean_slider=12, delay_kind_radio="tail", buffer_slider=3, delay_seed_input=9, seed_input=5)
    second = _at()
    for spec in P.SETTING_SPECS.values():
        pass
    for key, spec in P.SETTING_SPECS.items():
        second.query_params[spec.url_param] = spec.encoder(first.session_state[key])
    second.run()
    assert not second.exception
    assert _state_of(second) == _state_of(first)
    assert [m.value for m in second.main.metric][:4] == [m.value for m in first.main.metric][:4]


# ---------------- Seeds ----------------
def test_random_buttons_change_only_their_own_seed_and_the_fleet_stays_playable():
    at = _run()
    before = _state_of(at)
    _button(at, "🎲 Neue Verspätungen").click().run()
    assert not at.exception
    assert at.session_state["delay_seed_input"] != before["delay_seed_input"] and at.session_state["seed_input"] == before["seed_input"]
    _button(at, "🎲 Neue Schiffe").click().run()
    assert not at.exception
    assert at.session_state["seed_input"] != before["seed_input"]
    fleet = [at.session_state[k] for k in P.FLEET_KEYS]
    assert is_playable(P.fleet_instance(*fleet, at.session_state["seed_input"]))


def test_new_ships_button_only_draws_playable_fleets_even_when_most_fleets_do_not_fit():
    at = _run(n_ships_slider=10, quay_length_slider=500)
    fleet_before = [at.session_state[k] for k in P.FLEET_KEYS]
    for _ in range(3):
        _button(at, "🎲 Neue Schiffe").click().run()
        assert not at.exception
        assert is_playable(P.fleet_instance(*fleet_before, at.session_state["seed_input"]))
        assert not at.warning or not any("passt mindestens ein Schiff" in w.value for w in at.warning)


def test_unplayable_fleet_shows_a_warning_stops_the_page_and_the_search_button_repairs_it():
    fleet = (10, 500, 30, 14, 30)
    bad = next(s for s in range(200) if not is_playable(P.fleet_instance(*fleet, s)))
    at = _run(n_ships_slider=10, quay_length_slider=500, seed_input=bad)
    warn = [w for w in at.warning if "passt mindestens ein Schiff" in w.value]
    assert len(warn) == 1
    assert not [m for m in at.main.metric] and not at.get("plotly_chart") and not at.expander        # Seite endet vor der Auswertung
    assert at.sidebar.slider                                                                          # Seitenleiste bleibt bedienbar
    _button(at, "🔎 Passende Flotte suchen").click().run()
    assert not at.exception
    assert is_playable(P.fleet_instance(*fleet, at.session_state["seed_input"]))
    assert not [w for w in at.warning if "passt mindestens ein Schiff" in w.value] and at.get("plotly_chart")


# ---------------- Regler an den Grenzen ----------------
@pytest.mark.parametrize("key,which", [(k, w) for k in ("n_ships_slider", "arrival_spread_slider", "handling_avg_slider", "mainliner_slider",
                                                          "delay_mean_slider", "buffer_slider", "forecast_slider") for w in ("lo", "hi")])
def test_sliders_at_min_and_max_run_without_exception(key, which):
    lo, hi = P.bounds(key)
    at = _at(**{key: lo if which == "lo" else hi})
    at.run()
    assert not at.exception, [str(e) for e in at.exception]
    assert at.get("plotly_chart") or any("passt mindestens ein Schiff" in w.value for w in at.warning)


@pytest.mark.parametrize("quay", [500, 900])
def test_quay_length_extremes_either_run_or_show_the_fit_warning(quay):
    at = _run(quay_length_slider=quay)
    assert at.get("plotly_chart") or any("passt mindestens ein Schiff" in w.value for w in at.warning)


@pytest.mark.parametrize("kind", C.DELAY_KINDS)
def test_both_delay_kinds_run(kind):
    at = _run(delay_kind_radio=kind, delay_mean_slider=8)
    assert at.get("plotly_chart")


def test_buffer_zero_makes_the_buffer_strategy_identical_to_the_static_plan_in_the_main_view():
    at = _run(buffer_slider=0)
    metrics = [m for m in at.main.metric][:4]
    assert metrics[0].value == metrics[1].value and metrics[1].delta == "0.0 h"


def test_primary_view_offers_the_pdf_download():
    at = _run()
    buttons = at.get("download_button")
    assert len(buttons) == 1 and buttons[0].proto.label == "📄 Ergebnis als PDF herunterladen"
    assert buttons[0].proto.url                                                          # eine Datei hängt dran (Medien-URL)
