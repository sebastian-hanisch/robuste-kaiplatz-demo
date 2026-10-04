"""
Robuste Kaiplatzplanung – interaktive Fall-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Fortsetzung der Kaiplatz-Zuteilung (berth-allocation-demo) in der Hafen-Linie: Dort kommen alle Schiffe pünktlich. Hier kommen sie es nicht.
Frage: Was hilft gegen Verspätungen - Reserve im Plan (Puffer) oder Wissen im Betrieb (Neuplanung, mit Prognose)?

Lauffähig mit: streamlit run app.py
"""

import pandas as pd
import streamlit as st

import rb_constants as C
from rb_delays import scenario_delays
from rb_evaluation import (comparison_rows, delay_sweep, distribution, key_figures, outcome_of, run_strategies, verdict)
from rb_exact import price_of_uncertainty, solve_clairvoyant
from rb_pdf_export import generate_kai_pdf
from rb_presets import (apply_preset, bounds, find_playable_seed, fleet_instance, init_session_state_defaults, load_permalink_settings,
                        randomize_delay_seed, randomize_seed, sync_query_params, SETTING_SPECS)
from rb_scenario import is_playable
from rb_ui_panel import render_exact_panel, render_strategy_panel
from rb_visualization import berth_figure, comparison_figure, cost_curve_figure, distribution_figure, gain_figure, time_axis_end

st.set_page_config(page_title="Robuste Kaiplatzplanung – Sebastian Hanisch", layout="wide")

SCENARIO_KEYS = list(SETTING_SPECS)


@st.cache_data(show_spinner=False, max_entries=32)
def _compute_scenario(key):
    n_ships, quay, spread, handling, mainliner, seed, delay_mean, kind, delay_seed, buffer_h, forecast_pct = key
    inst = fleet_instance(n_ships, quay, spread, handling, mainliner, seed)
    delays = scenario_delays(inst, delay_mean, kind, delay_seed)
    return inst, delays, run_strategies(inst, delays, delay_mean, buffer_h, forecast_pct)


@st.cache_data(show_spinner=False, max_entries=8)
def _compute_focus(fleet, kind, delay_mean, buffer_h, forecast_pct):
    """Fokus-Stichprobe beim eingestellten delay: mehr Szenarien als die Kurve, ohne Hellsehen (Verteilung, Urteil, Gewinne)."""
    n_ships, quay, spread, handling, mainliner = fleet
    return delay_sweep(n_ships, quay, spread, handling, mainliner / 100, kind, delay_mean, buffer_h, forecast_pct,
                       n_instances=C.FOCUS_INSTANCES, n_draws=C.FOCUS_DRAWS, deltas=(delay_mean,), with_exact=False)


@st.cache_data(show_spinner=False, max_entries=8)
def _compute_exact(key):
    """Hellsehen läuft nur auf Klick (im eigenen Tab)."""
    n_ships, quay, spread, handling, mainliner, seed, delay_mean, kind, delay_seed = key
    inst = fleet_instance(n_ships, quay, spread, handling, mainliner, seed)
    return solve_clairvoyant(inst, scenario_delays(inst, delay_mean, kind, delay_seed), C.EXACT_TIME_LIMIT_SECONDS)


st.title("🚢 Robuste Kaiplatzplanung: Puffer oder Information?")
st.markdown(
    """
Schiffe kommen selten, wann der Fahrplan sagt - und ein Kaiplan muss damit leben. Diese Demo setzt die Kaiplatz-Zuteilung fort, in der alle
pünktlich waren: Die Wartezeit zählt jetzt ab der **tatsächlichen** Ankunft. Zwei Antworten auf die Unpünktlichkeit stehen gegeneinander:
**Reserve im Plan** (Puffer) oder **Wissen im Betrieb** (Neuplanung, mit einer Prognose der Restverspätung sogar besser). Wie das Modell funktioniert,
steht im Expander "Wie funktioniert diese Demo?" weiter unten, die formale Herleitung im Expander "📐 Mathematische Formulierung".
"""
)

st.caption("🎯 Schnellstart – ein Beispielszenario laden:")
PRESET_HELP = {
    "Pünktlich": "Alle Schiffe kommen wie geplant - hier kostet nur der Puffer, der Lücken lässt, die niemand braucht.",
    "Leichte Verspätung": "Im Mittel vier Stunden zu spät - kaum ein Unterschied, ein Puffer lohnt nicht.",
    "Große Verspätung": "Im Mittel zwölf Stunden zu spät - die Neuplanung gewinnt klar, mit Prognose noch mehr.",
    "Ausreißer": "Die meisten Schiffe pünktlich, wenige sehr spät (gleicher Mittelwert): Hier zählt die Neuplanung besonders.",
    "Ruhiger Hafen": "Wenige Schiffe, viel Platz, große Verspätung: der Fall, in dem sich ein Puffer lohnen kann.",
}
# Je Zeile drei Schaltflächen: bei fünf in einer Zeile werden die Namen in schmalen Fenstern abgeschnitten.
preset_names = list(C.PRESETS.keys())
for row_start in range(0, len(preset_names), 3):
    row = st.columns(3)
    for col, name in zip(row, preset_names[row_start:row_start + 3]):
        with col:
            st.button(name, width="stretch", on_click=apply_preset, args=(name,), help=PRESET_HELP[name])

st.caption(
    "🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, "
    "um ein Szenario zu teilen."
)

load_permalink_settings()
init_session_state_defaults()

with st.sidebar:
    st.header("⚙️ Einstellungen")
    n_ships = st.slider("Anzahl Schiffe", *bounds("n_ships_slider"), key="n_ships_slider",
                        help="Bis 10 Schiffe rechnet der Exakt-Löser (Hellsehen) in Sekundenbruchteilen; darüber wird er zäh.")
    quay_length = st.slider("Kailänge (m)", *bounds("quay_length_slider"), step=10, key="quay_length_slider",
                            help="Je kürzer der Kai, desto knapper. Unter etwa 550 m passen die längsten Schiffe oft nicht mehr an den Kai; "
                            "dann meldet die Demo es und sucht auf Knopfdruck eine passende Flotte.")
    arrival_spread = st.slider("Ankunftsfenster (h)", *bounds("arrival_spread_slider"), key="arrival_spread_slider",
                               help="Über wie viele Stunden die Fahrplan-Ankünfte verteilt sind. Klein = voller Hafen, groß = ruhiger Hafen.")
    handling_avg = st.slider("Ø Liegezeit (h)", *bounds("handling_avg_slider"), key="handling_avg_slider",
                             help="Mittlere Belegungsdauer eines Schiffs am Kai.")
    mainliner_pct = st.slider("Anteil Mainliner (%)", *bounds("mainliner_slider"), step=5, format="%d%%", key="mainliner_slider",
                              help="Mainliner haben das Gewicht 3, Feeder 1,5, Tramp 1 in der gewichteten Wartezeit.")
    seed = st.number_input("Seed der Schiffe", *bounds("seed_input"), key="seed_input", step=1,
                           help="Bestimmt die Flotte (Längen, Tiefgänge, Fahrplan-Ankünfte, Klassen). Unabhängig vom Seed der Verspätungen.")

    st.markdown("**Verspätungen**")
    delay_mean = st.slider("Mittlere Verspätung (h)", *bounds("delay_mean_slider"), key="delay_mean_slider",
                           help="0 = alle Schiffe pünktlich. Verspätungen sind nie negativ: Es gibt keine Verfrühung.")
    delay_kind = st.radio("Verspätungsart", list(C.DELAY_KINDS), format_func=C.DELAY_KIND_LABELS.get, key="delay_kind_radio", horizontal=True,
                          help="Gleichmäßig: exponentialverteilt mit dem eingestellten Mittel. Ausreißer: 80 % pünktlich, 20 % sehr spät - "
                          "bei gleichem Mittelwert.")
    delay_seed = st.number_input("Seed der Verspätungen", *bounds("delay_seed_input"), key="delay_seed_input", step=1,
                                 help="Bestimmt die Ziehung der Verspätungen. Unabhängig vom Seed der Schiffe.")

    st.markdown("**Strategien**")
    buffer_h = st.slider("Puffer (h)", *bounds("buffer_slider"), key="buffer_slider",
                         help="Nur für die Strategie 'Puffer': Der Plan rechnet mit einer um so viele Stunden längeren Liegezeit. 0 = identisch mit starr.")
    forecast_pct = st.slider("Prognose (% der mittleren Verspätung)", *bounds("forecast_slider"), step=C.FORECAST_PCT_STEP, format="%d%%",
                             key="forecast_slider",
                             help="Nur für 'Neuplanung + Prognose': Noch nicht angekommene Schiffe werden erst nach dieser erwarteten Restverspätung "
                             "eingeplant. 100 % = richtige Prognose, 200 % = doppelt zu pessimistisch, 0 % = nur die Fahrplan-Ankunft. "
                             "Ohne mittlere Verspätung (0 h) gibt es nichts zu prognostizieren, dann ändert der Regler nichts.")

    st.button("🎲 Neue Schiffe", width="stretch", on_click=randomize_seed,
              help="Würfelt einen neuen Seed für die Flotte (nur Flotten, die an den Kai passen).")
    st.button("🎲 Neue Verspätungen", width="stretch", on_click=randomize_delay_seed, help="Würfelt einen neuen Seed für die Verspätungen.")

sync_query_params({key: st.session_state[key] for key in SCENARIO_KEYS})

fleet = (int(n_ships), int(quay_length), int(arrival_spread), int(handling_avg), int(mainliner_pct))
delay_mean, buffer_h, forecast_pct = int(delay_mean), int(buffer_h), int(forecast_pct)
scenario_key = fleet + (int(seed), delay_mean, delay_kind, int(delay_seed), buffer_h, forecast_pct)

if not is_playable(fleet_instance(*fleet, int(seed))):
    st.warning(
        "⚠️ Mit diesen Einstellungen passt mindestens ein Schiff an keine Kaizone (zu lang oder zu tief für die Zone). "
        "Den Kai verlängern, weniger Schiffe wählen oder eine passende Flotte suchen lassen."
    )
    st.button("🔎 Passende Flotte suchen", on_click=find_playable_seed, help="Setzt den Seed der Schiffe auf den nächsten, bei dem alle Schiffe passen.")
    st.stop()

with st.spinner("Führe die Strategien aus..."):
    instance, delays, outcomes = _compute_scenario(scenario_key)
with st.spinner(f"Rechne {C.FOCUS_INSTANCES * C.FOCUS_DRAWS} Szenarien mit Ihren Einstellungen..."):
    focus = _compute_focus(fleet, delay_kind, delay_mean, buffer_h, forecast_pct)

S, P, N, F, X = C.STRAT_STARR, C.STRAT_PUFFER, C.STRAT_NEU, C.STRAT_PROGNOSE, C.STRAT_EXACT
baseline = outcome_of(outcomes, S)
t_end = time_axis_end(instance, *[o.execution for o in outcomes])
dist = {k: distribution(focus, k, delay_mean) for k in (P, N, F)}

# ---------------------------------------------------------------------------------------------------
# Hauptansicht
# ---------------------------------------------------------------------------------------------------
st.markdown("## 🎯 Was kosten die Verspätungen in diesem Szenario?")
st.caption("Gewichtete Wartezeit je Schiff, gezählt ab der **tatsächlichen** Ankunft. Alle vier Strategien sehen dieselben Verspätungen.")

metric_rows = [st.columns(2), st.columns(2)]                  # 2 x 2: vier Spalten schneiden die Namen bei 800 px ab
for col, o in zip(metric_rows[0] + metric_rows[1], outcomes):
    is_ref = o.key == baseline.key
    diff = o.wait_per_ship - baseline.wait_per_ship
    same = abs(diff) < 0.05
    col.metric(
        o.label, f"{o.wait_per_ship:.1f} h",
        delta=None if is_ref else ("0.0 h" if same else f"{diff:+.1f} h"), delta_color="off" if same else "inverse",
        help="Referenz für alle Vergleiche." if is_ref else "Differenz: diese Strategie minus starrer Plan (weniger Wartezeit ist besser).",
    )

mine_n = outcome_of(outcomes, N).wait_total - baseline.wait_total
this_draw = "besser als" if mine_n < -0.5 else ("schlechter als" if mine_n > 0.5 else "gleich gut wie")
dn = dist[N]
st.info(
    f"ℹ️ Das ist **eine** Ziehung der Verspätungen (Seed {int(delay_seed)}): Hier ist die Neuplanung **{this_draw}** der starre Plan. "
    f"Im Kernabschnitt darunter, über {focus.n_scenarios} Szenarien mit Ihren Einstellungen, ist sie in **{dn.better * 100:.0f} %** der Fälle besser, "
    f"in {dn.equal * 100:.0f} % gleich und in **{dn.worse * 100:.0f} %** schlechter - der Mittelwert allein täuscht."
)
if delay_mean == 0:
    st.caption("Ohne Verspätung gibt es nichts zu retten: Die Neuplanung ist so gut wie der Plan, der Puffer kostet nur Lücken.")

st.markdown("#### 🔍 Blick an den Kai")
right_key = st.radio(
    "Rechts vergleichen mit", [P, N, F], index=2, format_func=C.STRATEGY_LABELS.get, key="kai_view_radio", horizontal=True,
    help="Links steht immer der starre Plan.",
)
right = outcome_of(outcomes, right_key)
left_col, right_col = st.columns(2)
for col, o, side in ((left_col, baseline, "left"), (right_col, right, "right")):
    with col:
        st.markdown(f"**{o.label}**")
        st.plotly_chart(berth_figure(instance, o.execution.plan, o.execution.arrivals, t_end=t_end), width="stretch", key=f"kai_chart_{side}")
st.caption(
    "Balken = tatsächliche Belegung (Zahl = Schiffsnummer, Farbe = Klasse). ▽ Fahrplan-Ankunft, ◆ tatsächliche Ankunft, orange Strecke = Verspätung, "
    "gepunktete Linie = Wartezeit bis zum Anlegen. Beide Diagramme haben dieselbe Zeitachse."
)

st.download_button(
    "📄 Ergebnis als PDF herunterladen",
    data=generate_kai_pdf(
        instance, outcomes,
        dict(n_ships=fleet[0], quay_length=fleet[1], arrival_spread=fleet[2], handling_avg=fleet[3], mainliner_pct=fleet[4], seed=int(seed),
             delay_mean=delay_mean, delay_kind=delay_kind, delay_seed=int(delay_seed), buffer=buffer_h, forecast_pct=forecast_pct),
        shares=(dn.better, dn.equal, dn.worse)),
    file_name="kaiplatz_ergebnis.pdf", mime="application/pdf", key="primary_pdf_download",
)

st.caption(
    f"Ausgeführt mit den Seeds {int(seed)} (Schiffe) und {int(delay_seed)} (Verspätungen). Was im Mittel gilt und wie stark ein Einzelfall davon abweichen kann, "
    "zeigt der Kernabschnitt darunter; Details zu allen Strategien und der Vergleich mit dem Optimum stehen im Methodenvergleich."
)

st.markdown("---")

# ---------------------------------------------------------------------------------------------------
# Kernabschnitt
# ---------------------------------------------------------------------------------------------------
st.subheader("📐 Puffer oder Information? Was ist was wert?")
st.markdown(
    """
Kernfrage dieser Demo: Lohnt sich **Reserve im Plan** (Puffer) oder **Wissen im Betrieb** (Neuplanung)? Ein Puffer kostet immer - auch bei pünktlichen
Schiffen. Die Neuplanung kostet keine Lücken, nutzt aber nur, was schon bekannt ist; mit einer **Prognose** der Restverspätung plant sie noch besser.
Hier live für Ihre Einstellungen gerechnet (nicht nur behauptet), und **mit der Verteilung dazu**, denn bei schiefen Gewinnen täuscht der Mittelwert:
"""
)


def _gain(key):
    return focus.mean(S, 0) - focus.mean(key, 0), 100 * (focus.mean(S, 0) - focus.mean(key, 0)) / focus.mean(S, 0) if focus.mean(S, 0) else None


st.markdown("**Gewinn gegen den starren Plan** (Mittel je Schiff, positiv = weniger Wartezeit):")
g1, g2, g3 = st.columns(3)
for col, key, label in ((g1, P, "Puffer"), (g2, N, "Neuplanung"), (g3, F, "+ Prognose")):
    gain, pct = _gain(key)
    col.metric(
        label, f"{gain:+.2f} h",
        delta=None if pct is None else ("0 %" if abs(pct) < 0.5 else f"{pct:+.0f} %"), delta_color="off" if pct is not None and abs(pct) < 0.5 else "normal",
        help=f"Mittel über {focus.n_scenarios} Szenarien beim eingestellten delay (positiv = weniger Wartezeit als der starre Plan). "
        f"Typisch (Median) je Szenario: {dist[key].median_gain:+.1f} h Gesamtwartezeit, Mittel {dist[key].mean_gain:+.1f} h.",
    )


def _show_verdict(label, subject, key, reference, ref_label):
    v = verdict(focus, key, delay_mean, baseline=reference)
    d = distribution(focus, key, delay_mean, baseline=reference)
    tail = (f" Einzelne Szenarien weichen ab: In **{d.worse * 100:.0f} %** ist das Ergebnis schlechter, in {d.better * 100:.0f} % besser "
            f"(Median-Gewinn {d.median_gain:+.1f} h gegen Mittel {d.mean_gain:+.1f} h je Szenario).")
    if v.kind == "better":
        st.success(f"✅ **{label}** lohnt sich hier: im Mittel **{abs(v.pct or 0):.0f} % weniger** Wartezeit gegenüber {ref_label} "
                   f"({-v.diff:.2f} h je Schiff, Standardfehler {v.se:.2f}).{tail}")
    elif v.kind == "worse":
        st.warning(f"⚠️ **{label}** kostet hier mehr, als sie bringt: im Mittel **{abs(v.pct or 0):.0f} % mehr** Wartezeit gegenüber {ref_label} "
                   f"({v.diff:.2f} h je Schiff, Standardfehler {v.se:.2f}).{tail}")
    else:
        st.info(f"ℹ️ Kein klarer Unterschied zwischen **{subject}** und {ref_label}: die Differenz ({v.diff:+.2f} h je Schiff) liegt innerhalb des "
                f"Rauschens (Standardfehler {v.se:.2f}).{tail}")


_show_verdict("Der Puffer", "Puffer", P, S, "dem starren Plan")
_show_verdict("Die Neuplanung", "Neuplanung", N, S, "dem starren Plan")
_show_verdict("Die Prognose", "Prognose und Neuplanung", F, N, "der Neuplanung ohne Prognose")

dcol1, dcol2 = st.columns(2)
with dcol1:
    st.markdown("**Wie sich die Gewinne verteilen** (Anteil der Szenarien)")
    st.plotly_chart(distribution_figure([dist[P], dist[N], dist[F]]), width="stretch", key="distribution_chart")
with dcol2:
    st.markdown("**Typisches Szenario gegen Mittelwert**")
    st.plotly_chart(gain_figure([dist[P], dist[N], dist[F]]), width="stretch", key="gain_chart")
st.caption(
    f"Basis: {C.FOCUS_INSTANCES} Flotten (Seeds 0-{C.FOCUS_INSTANCES - 1}) x {C.FOCUS_DRAWS} Verspätungs-Ziehungen mit Ihren Hafen- und Verspätungseinstellungen - "
    "nicht Ihr aktueller Seed. Gleich heißt: Unterschied höchstens eine halbe gewichtete Wartestunde. Liegt der Median weit unter dem Mittelwert, "
    "tragen wenige Szenarien den Gewinn."
)

st.markdown("##### Kostenkurve über die mittlere Verspätung")
curve_key = fleet + (delay_kind, buffer_h, forecast_pct)
st.caption(
    "Die Kurve rechnet alle fünf Strategien über den ganzen Verspätungsbereich, auch das Hellsehen - das dauert je nach Schiffszahl etwa 10 bis 40 Sekunden "
    "und läuft deshalb auf Knopfdruck. Sie hängt nicht von den Seeds und nicht vom eingestellten delay ab."
)
if st.button("📈 Kostenkurve berechnen", key="rb_curve_btn"):
    bar = st.progress(0.0, text="Rechne die Kurve ...")
    try:
        curve_new = delay_sweep(fleet[0], fleet[1], fleet[2], fleet[3], fleet[4] / 100, delay_kind, 0, buffer_h, forecast_pct,
                                progress=lambda f: bar.progress(min(1.0, f), text=f"Rechne die Kurve ... {f * 100:.0f} %"))
        st.session_state["rb_curve"] = (curve_key, curve_new)
    except ValueError as err:
        st.warning(f"Die Kurve lässt sich mit diesen Einstellungen nicht rechnen: {err}")
    bar.empty()

stored = st.session_state.get("rb_curve")
if stored is not None and stored[0] == curve_key:
    curve = stored[1]
    kf = key_figures(curve, focus, delay_mean)
    k1, k2, k3 = st.columns(3)
    k1.metric("Puffer-Aufpreis", "—" if kf.buffer_price_at_zero_pct is None else f"{kf.buffer_price_at_zero_pct:+.0f} %",
              help="Mehrkosten des Puffers bei pünktlichen Schiffen gegenüber dem starren Plan, also ohne jede Verspätung (Kurve bei delay 0).")
    k2.metric("Puffer lohnt ab", "nie im Bereich" if kf.tipping_point is None else f"{kf.tipping_point:.1f} h",
              help="Mittlere Verspätung, ab der der Puffer im Mittel besser ist als der starre Plan (lineare Interpolation zwischen den Rasterpunkten). "
              "In ausgelasteten Häfen gibt es ihn oft nicht.")
    k3.metric("Unsicherheitspreis", f"{kf.price_of_uncertainty:.1f} h",
              help=f"Preis der Unsicherheit je Schiff bei {kf.delay:g} h Verspätung (nächster Rasterpunkt zum eingestellten Wert): starrer Plan minus Hellsehen, "
              "also so viel Wartezeit kostet es, die Ankünfte nicht im Voraus zu kennen.")
    st.plotly_chart(cost_curve_figure(curve, delay_mean, kf.tipping_point), width="stretch", key="cost_curve_chart")
    st.caption(
        f"Basis: {curve.n_scenarios // C.SWEEP_DRAWS} Flotten (Seeds 0-{curve.n_scenarios // C.SWEEP_DRAWS - 1}) x {C.SWEEP_DRAWS} Ziehungen je Punkt; Band = ± 1 Standardfehler. "
        "Die Kosten des **Hellsehens sinken mit der Verspätung**: Gezählt wird nur die Wartezeit im Hafen, und verspätete Ankünfte entzerren den Kai. "
        "Die Kurve zeigt, wie gut eine Strategie damit umgeht - nicht, dass Verspätung gut wäre."
    )
    if curve.unproven:
        st.caption(f"⏱️ Bei {curve.unproven} Szenarien der Kurve wurde das Hellsehen im Zeitlimit nicht bewiesen; dort ist der Wert eine Obergrenze des Optimums.")
elif stored is not None:
    st.info("ℹ️ Die zuletzt berechnete Kurve bezog sich auf andere Hafen-, Verspätungs- oder Strategie-Einstellungen. Erneut auf '📈 Kostenkurve berechnen' klicken.")
else:
    st.info("Noch nichts berechnet – auf den Button oben klicken.")

st.markdown("---")

# ---------------------------------------------------------------------------------------------------
# Methodenvergleich
# ---------------------------------------------------------------------------------------------------
with st.expander("🔧 Wie wir das erreichen – vollständiger Methodenvergleich"):
    tabs = st.tabs([o.label for o in outcomes] + ["🧮 Exakt (Hellsehen)", "📊 Vergleich"])
    for tab, outcome in zip(tabs[: len(outcomes)], outcomes):
        with tab:
            render_strategy_panel(f"strategy_{outcome.key}", outcome, outcomes, instance, t_end)

    tab_exact, tab_compare = tabs[len(outcomes)], tabs[len(outcomes) + 1]
    exact_key = fleet + (int(seed), delay_mean, delay_kind, int(delay_seed))
    exact_result = None
    with tab_exact:
        st.caption(
            "Hellsehen: der beste Plan, den man mit Kenntnis ALLER tatsächlichen Ankünfte im Voraus wählen würde (CP-SAT, wie in der Kaiplatz-Zuteilung). "
            "Keine Strategie kann das erreichen - es ist die untere Schranke, und der Abstand dazu ist der Preis der Unsicherheit. "
            f"Auf {C.EXACT_TIME_LIMIT_SECONDS:g} s begrenzt; läuft das Zeitlimit ab, steht das dabei (nie ein unbewiesener Wert als Optimum)."
        )
        if st.button("🧮 Hellsehen berechnen", key="rb_exact_btn"):
            st.session_state["rb_exact_scenario_key"] = exact_key
        if st.session_state.get("rb_exact_scenario_key") == exact_key:
            with st.spinner(f"Exakte Suche (bis zu {C.EXACT_TIME_LIMIT_SECONDS:g} s)..."):
                exact_result = _compute_exact(exact_key)
            render_exact_panel("exact", instance, exact_result, outcomes, {i: baseline.execution.arrivals[i] for i in baseline.execution.arrivals}, t_end)
        elif "rb_exact_scenario_key" in st.session_state:
            st.info("ℹ️ Die zuletzt berechnete exakte Lösung bezog sich auf ein anderes Szenario - Einstellungen geändert? "
                    "Erneut auf '🧮 Hellsehen berechnen' klicken.")
        else:
            st.info("Noch nichts berechnet – auf den Button oben klicken.")

    with tab_compare:
        rows = comparison_rows(outcomes)
        table = [{
            "Strategie": r.label, "Wartezeit gewichtet (h)": round(r.wait_total, 1), "je Schiff (h)": round(r.wait_per_ship, 2),
            **{f"Ø Wartezeit {p} (h)": (round(r.wait_by_priority[p], 1) if p in r.wait_by_priority else None) for p in C.PRIORITIES},
            "Neuplanungen": r.replans, "Positionswechsel": r.position_changes,
            f"Differenz zu '{baseline.label}' (h)": round(r.delta_vs_baseline, 1),
        } for r in rows]
        if exact_result is not None:
            table.append({
                "Strategie": C.STRATEGY_LABELS[X] + ("" if exact_result.proven else " (nicht bewiesen)"),
                "Wartezeit gewichtet (h)": round(exact_result.weighted_wait, 1),
                "je Schiff (h)": round(exact_result.weighted_wait / len(instance.ships), 2),
                f"Differenz zu '{baseline.label}' (h)": round(exact_result.weighted_wait - baseline.wait_total, 1),
            })
        st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
        st.plotly_chart(comparison_figure(outcomes), width="stretch", key="comparison_chart")
        if exact_result is None:
            st.caption("Das Hellsehen erscheint hier, sobald es im Tab '🧮 Exakt' berechnet wurde.")
        else:
            st.caption("Preis der Unsicherheit je Strategie (Wartezeit minus Hellsehen): " + ", ".join(
                f"{o.label} {price_of_uncertainty(o.wait_total, exact_result):.0f} h" for o in outcomes))

with st.expander("Wie funktioniert diese Demo?"):
    st.markdown(
        """
**Fahrplan gegen Wirklichkeit.** Jedes Schiff hat eine **Fahrplan-Ankunft** (ETA). Tatsächlich kommt es um seine **Verspätung** später - nie früher.
Gezählt wird die Wartezeit ab der **tatsächlichen** Ankunft, gewichtet nach Klasse (Mainliner 3, Feeder 1,5, Tramp 1). Der Kai hat zwei Tiefenzonen; ein Schiff
liegt vollständig in einer Zone, die tief genug ist, mit Sicherheitsabstand zu seinen Nachbarn. Der Hafen ist fest, die Flotte einstellbar.

**Vier Strategien**, alle mit denselben Verspätungen:

- **Starrer Plan**: Der Plan wird auf den Fahrplan-Ankünften gemacht und dann ausgeführt. Positionen und Reihenfolge am Kai bleiben; ein verspätetes Schiff
  schiebt alle nach, die räumlich hinter ihm liegen (**Rechts-Verschiebung**). Kein Anlegen vor dem geplanten Fenster.
- **Puffer**: Der Plan rechnet mit einer um den Puffer verlängerten Liegezeit und lässt so Lücken. Sie kosten Wartezeit, auch wenn alle pünktlich sind.
- **Neuplanung**: Bei jeder Ankunft und wenn ein geplantes Fenster ohne Schiff verstreicht, werden alle noch nicht liegenden Schiffe neu eingeplant. Liegende Schiffe
  sind feste Hindernisse; noch nicht angekommene zählen ab ihrer Fahrplan-Ankunft, frühestens ab der nächsten Stunde. Eingesetzt wird die Einfüge-Heuristik der
  Kaiplatz-Zuteilung mit Tausch-Suche (in der Messreihe war sie bei 40 Suchzügen gesättigt; ein exakter Löser für die Neuplanung brachte nur etwa 1 bis 7 % mehr).
- **Neuplanung + Prognose**: wie die Neuplanung, aber noch nicht angekommene Schiffe werden erst nach der **erwarteten Restverspätung** eingeplant (Regler: Anteil der mittleren
  Verspätung). Die Prognose ist robust: Selbst eine doppelt zu pessimistische ist im Mittel besser als keine.

Dazu das **Hellsehen** (Tab "Exakt"): der beste Plan bei Kenntnis aller tatsächlichen Ankünfte, eine untere Schranke, die keine Strategie erreicht. Der Abstand dazu ist der
**Preis der Unsicherheit**.

**Kai-Diagramm lesen.** Balken = tatsächliche Belegung (Breite = Liegezeit, Höhe = Schiffslänge), Zahl = Schiffsnummer. ▽ = Fahrplan-Ankunft, ◆ = tatsächliche Ankunft, orange
Strecke dazwischen = Verspätung, gepunktete Linie = Wartezeit bis zum Anlegen.

**Warum ein Einzelfall vom Mittelwert abweicht.** Die Gewinne der Neuplanung sind **schief verteilt**: In vielen Szenarien ändert sich wenig, in wenigen sehr viel. Der Mittelwert wird von diesen
wenigen getragen, der Median ist das typische Szenario, und in einem Teil der Szenarien ist die Neuplanung sogar **schlechter** als der starre Plan (sie optimiert jeweils mit dem, was sie
weiß, und kann sich dadurch später verbauen). Deshalb zeigt der Kernabschnitt die Verteilung und nennt einen Unterschied nur dann klar, wenn er mehr als zwei Standardfehler beträgt.

**Warum die Kosten des Hellsehens mit der Verspätung sinken.** Gezählt wird nur die Wartezeit im Hafen ab tatsächlicher Ankunft. Verspätete Ankünfte entzerren den Kai, also wartet man
weniger - die Verspätung selbst (verpasste Anschlüsse, Reederkosten) ist nicht bepreist. Die Kurve zeigt, wie gut eine Strategie mit dieser Entzerrung umgeht, nicht dass Verspätung gut wäre.

**Was die Neuplanung an Stabilität kostet.** Kaipositionen ändern sich kaum (meist eines von neun Schiffen), aber die Neuplanung plant je Szenario sechs- bis vierzigmal neu, und
die angekündigten Anlegezeiten wandern. Diese Unruhe wird gezählt (Kennzahlen im Methodenvergleich), aber nicht bepreist.

**Kurve und Kernabschnitt** rechnen für Ihre Hafengröße über je 30 bis 90 Szenarien (Flotten mit den Seeds 0, 1, 2, ... gegen Ziehungen), nicht mit Ihrem aktuellen Seed. Der **Kipppunkt** ist die
mittlere Verspätung, ab der ein Puffer im Mittel besser ist als der starre Plan; in ausgelasteten Häfen gibt es ihn oft nicht.

**Grenzen dieses Modells** (bewusst so gewählt, damit die Aussage ehrlich bleibt):

- Es gibt **nur Verspätungen, keine Verfrühung**, eine **feste Liegezeit** (kein Kranzahl-Effekt, siehe quaycrane-demo) und **einen Kai**.
- Die **Neuplanung ist kostenlos und sofort umsetzbar**: Lotsen, Schlepper, Mannschaften und Vorlaufzeiten sind nicht modelliert. Die Unruhe im Plan wird gezählt, nicht bepreist.
- Die **starre Ausführung ist bewusst einfach** (Rechts-Verschiebung). Eine klügere starre Ausführung nähert sich der Neuplanung.
- Die **Verspätungsverteilungen sind Annahmen**, keine Echtdaten. Zwei Arten mit gleichem Mittelwert zeigen, wie sehr der Rand zählt.
- Der **Hafen ist fest** (Zonen, Tiefgänge, Sicherheitsabstand); unter etwa 550 m Kailänge passen die längsten Schiffe oft nicht an den Kai.
- Alle Zahlen sind **Größenordnungen aus einer Simulation, keine Messung an Echtdaten.**
        """
    )

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        r"""
**Robuste Kaiplatzplanung mit verspäteten Ankünften** (dynamisches Berth Allocation Problem, NP-schwer).

Gegeben Schiffe $i = 1, \dots, n$ mit Länge $\ell_i$, Tiefgang, Fahrplan-Ankunft $a_i$, Liegezeit $h_i$ und Gewicht $w_i$; ein Kai aus Zonen mit Tiefgangsgrenzen und ein
Sicherheitsabstand $m$. Ein **Plan** ordnet jedem Schiff Anlegebeginn $s_i$ und Position $p_i$ zu, sodass sich die Rechtecke
$[s_i, s_i + h_i) \times [p_i, p_i + \ell_i + m)$ nicht überlappen und jedes Schiff vollständig in einer ausreichend tiefen Zone liegt.

**Verspätung:** $a'_i = a_i + v_i$ mit ganzzahligem $v_i \ge 0$; gleichmäßig $v_i \sim \mathrm{Exp}(\delta)$ oder Ausreißer
($v_i = 0$ mit Wahrscheinlichkeit $0{,}8$, sonst $\mathrm{Exp}(5\delta)$), beide mit Mittelwert $\delta$. Es gilt $s_i \ge a'_i$.

**Zielgröße:** gewichtete Wartezeit ab tatsächlicher Ankunft
$$
\min \; \sum_i w_i \,(s_i - a'_i).
$$

**Rechts-Verschiebung** eines Plans $(t_i, p_i)$ auf den ETAs, Vorgänger $j \prec i$ heißt $t_j < t_i$ (bei Gleichstand kleinerer Index) mit räumlich überlappender Belegung:
$$
s_i = \max\Big(a'_i,\; t_i,\; \max_{j \prec i,\ \text{Ort überlappt}} (s_j + h_j)\Big).
$$

**Puffer $b$:** Plan für die Liegezeiten $h_i + b$, Ausführung wie oben mit den echten $h_i$.

**Neuplanung:** Zu jedem Ereignis $\tau$ (Ankunft, oder ein geplantes Fenster verstreicht ohne Schiff) kennt man die Schiffe mit $a'_i \le \tau$. Bereits liegende Schiffe sind feste Hindernisse
$(s_i, p_i)$. Für die übrigen wird ein Plan mit den **effektiven Ankünften**
$$
\tilde a_i = \begin{cases} \max(a'_i, \tau) & a'_i \le \tau \\ \max(a_i,\; \tau + r) & \text{sonst} \end{cases}
$$
gerechnet ($r = 1$: nur die ETA; $r > 1$: erwartete Restverspätung, im Regler als Anteil von $\delta$). Die Einfüge-Heuristik fügt die Schiffe nacheinander an der frühesten zulässigen
Stelle ein, eine Tausch-Suche über die Einfüge-Reihenfolge verbessert sie.

**Hellsehen:** CP-SAT mit den tatsächlichen Ankünften: Startzeit und Position je Schiff, ein `AddNoOverlap2D` über alle Rechtecke, Zielfunktion $\sum w_i (s_i - a'_i)$ mit der ungewichteten
Wartezeit als Tie-Break (Verweis auf die Kaiplatz-Zuteilung). Der Wert ist eine untere Schranke für jede Strategie, die nur ETAs und bisher eingetretene Ankünfte kennt.

**Vergleich über Szenarien:** Für Strategie $A$ gegen Referenz $B$ auf denselben Szenarien $k = 1, \dots, K$ (gleiche Verspätungen) ist $\Delta_k = c_B^{(k)} - c_A^{(k)}$ der Gewinn; berichtet werden
Mittel, Median, der Anteil der Szenarien mit $\Delta_k > 0{,}5$ (besser) bzw. $< -0{,}5$ (schlechter), und ein Unterschied gilt als klar, wenn $|\bar\Delta| > 2\,\mathrm{SE}(\Delta)$
mit der gepaarten Standardabweichung.

Implementiert in `rb_execution.py` (Ausführung), `rb_exact.py` (Hellsehen) und `rb_evaluation.py` (Vergleiche); Instanzen und Heuristik stammen wortgleich aus der Kaiplatz-Zuteilung.
        """
    )

st.markdown("---")

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). "
    "Mehr zum Thema: [Hafenlogistik optimieren](https://sebastianhanisch.net/hafenlogistik-optimierung.html)."
)
