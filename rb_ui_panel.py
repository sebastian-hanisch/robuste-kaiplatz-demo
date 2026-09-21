"""Wiederverwendbare Panels: je Strategie ein Tab im Methodenvergleich und der selbstständige Exakt-Tab (Hellsehen)."""

import streamlit as st

import rb_constants as C
from rb_evaluation import outcome_of
from rb_exact import price_of_uncertainty
from rb_visualization import berth_figure


def _delta(value, is_reference):
    return None if is_reference else f"{value:+.1f} h"


def render_strategy_panel(prefix, outcome, outcomes, inst, t_end):
    """Beschreibung, Kennzahlen und Kai-Diagramm einer Strategie. Deltas lesen sich immer als "diese Strategie minus starr"
    (delta_color="inverse": weniger Wartezeit ist besser). `prefix` macht die Widget-Schlüssel eindeutig."""
    ref = outcome_of(outcomes, C.BASELINE)
    is_ref = outcome.key == ref.key
    st.markdown(C.STRATEGY_DESCRIPTIONS[outcome.key])

    top, bottom = st.columns(2), st.columns(2)                      # 2 x 2: vier Spalten schneiden die Namen in schmalen Tabs ab
    m1, m2, m3, m4 = top + bottom
    m1.metric("Wartezeit gewichtet", f"{outcome.wait_total:.0f} h", delta=_delta(outcome.wait_total - ref.wait_total, is_ref), delta_color="inverse",
              help="Summe aus Gewicht x (Anlegebeginn - tatsächliche Ankunft) über alle Schiffe.")
    m2.metric("je Schiff", f"{outcome.wait_per_ship:.1f} h", delta=_delta(outcome.wait_per_ship - ref.wait_per_ship, is_ref), delta_color="inverse")
    m3.metric("Neuplanungen", f"{outcome.replans}", help="Wie oft der Plan im Ablauf neu gerechnet wurde (starr und Puffer: nie).")
    m4.metric("Positionswechsel", f"{outcome.position_changes}",
              help="Schiffe, die am Ende an einer anderen Kaiposition liegen als zu Beginn angekündigt.")
    st.caption(f"Der angekündigte Anlegebeginn verschiebt sich im Mittel um {outcome.window_shift:.1f} h.")

    fig = berth_figure(inst, outcome.execution.plan, outcome.execution.arrivals, t_end=t_end)
    st.plotly_chart(fig, width="stretch", key=f"{prefix}_berth_chart")


def render_exact_panel(prefix, inst, exact, outcomes, arrivals, t_end):
    """Ergebnis des Hellsehens: Optimum, Kennzeichnung "nicht bewiesen", Preis der Unsicherheit je Strategie und Kai-Diagramm des Optimums."""
    if exact.source != "CP-SAT":
        st.warning("Der Exakt-Löser hat im Zeitlimit keine Lösung gefunden; gezeigt wird der Plan der Einfüge-Heuristik auf den tatsächlichen Ankünften. "
                   "Er ist **nicht bewiesen** optimal, der Preis der Unsicherheit kann größer sein.")
    elif not exact.proven:
        st.warning("Das Zeitlimit lief ab: Der Plan ist **nicht bewiesen** optimal, der Preis der Unsicherheit kann größer sein als angezeigt.")
    else:
        st.caption(f"Bewiesen optimal (CP-SAT, {exact.wall_time_ms:.0f} ms).")

    st.metric("Hellsehen: gewichtete Wartezeit", f"{exact.weighted_wait:.0f} h" + ("" if exact.proven else " (nicht bewiesen)"),
              help="Untere Schranke: so wenig Wartezeit ist mit Kenntnis aller tatsächlichen Ankünfte im Voraus möglich.")
    st.markdown("**Preis der Unsicherheit** (Wartezeit der Strategie minus Hellsehen):")
    grid = st.columns(2) + st.columns(2)
    for col, o in zip(grid, outcomes):
        col.metric(o.label, f"{price_of_uncertainty(o.wait_total, exact):.0f} h")

    fig = berth_figure(inst, exact.plan, arrivals, t_end=t_end)
    st.plotly_chart(fig, width="stretch", key=f"{prefix}_berth_chart")
