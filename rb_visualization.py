"""Plotly-Diagramme: Kai-Belegung mit Fahrplan-Ankunft, tatsächlicher Ankunft und Wartelinie, Kostenkurve, Verteilung der Gewinne, Vergleich.

Konventionen des Portfolios: Achsen `fixedrange` (Touch-Scrollen), Vorlage plotly_white, Formen unter den Spuren (`layer="below"`), Markerlinien in mittlerem Grau
(im dunklen Schema sonst unsichtbar). Alle Funktionen sind reine Rechnung auf den Ergebnisobjekten; Streamlit kommt hier nicht vor."""

import math
from collections import namedtuple

import rb_constants as C

_Run = namedtuple("_Run", "plan arrivals")

LEGEND_TOP = dict(orientation="h", yanchor="bottom", y=1.02, x=0)
LEGEND_BOTTOM = dict(orientation="h", yanchor="top", y=-0.22, x=0)


def _lock_axes(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def time_axis_end(inst, *runs):
    """Gemeinsames Zeitachsen-Ende (auf ganze Tage aufgerundet), damit nebeneinanderstehende Kai-Diagramme vergleichbar sind.
    `runs`: Objekte mit `plan` (Index -> (Start, Position)) und `arrivals` (Index -> tatsächliche Ankunft)."""
    end = 1
    for run in runs:
        for i, (start, _pos) in run.plan.items():
            end = max(end, start + inst.ships[i].handling_time, run.arrivals[i])
    return int(math.ceil(end / 24.0)) * 24


# ---------------------------------------------------------------------------------------------------
# Kai-Diagramm
# ---------------------------------------------------------------------------------------------------
def _hover_points(x0, x1, y0, y1, nx=5, ny=3):
    """Unsichtbare Punkte über das ganze Rechteck: Plotly hovert Spuren nach dem nächsten DATENPUNKT, ein einzelner Mittelpunkt träfe nur die Mitte."""
    xs = [x0 + (x1 - x0) * (a + 0.5) / nx for a in range(nx)]
    ys = [y0 + (y1 - y0) * (b + 0.5) / ny for b in range(ny)]
    return [x for _ in ys for x in xs], [y for y in ys for _ in xs]


def berth_figure(inst, plan, arrivals, title="", t_end=None):
    """Kai im Zeit-Position-Raum. Balken = tatsächliche Belegung (Start, Position aus `plan`), ▽ = Fahrplan-Ankunft (nur bei Verspätung),
    ◆ = tatsächliche Ankunft, orange Strecke = Verspätung, gepunktete Linie = Wartezeit von der Ankunft bis zum Anlegen."""
    import plotly.graph_objects as go

    t_end = t_end or time_axis_end(inst, _Run(plan, arrivals))
    fig = go.Figure()
    for zone in inst.zones:
        fig.add_shape(type="rect", x0=0, x1=t_end, y0=zone.start, y1=zone.end,
                      fillcolor=C.ZONE_COLORS.get(zone.name, "rgba(0,0,0,0.05)"), line=dict(width=0), layer="below")
        fig.add_annotation(x=0, y=zone.end - 2, text=f"{zone.name} (max. {zone.max_draft:.1f} m Tiefgang)", showarrow=False,
                           xanchor="left", yanchor="top", font=dict(size=10, color=C.MARKER_LINE_COLOR), xshift=4)

    hover_x, hover_y, hover_text = [], [], []
    label_x, label_y, label_text = [], [], []
    eta_x, eta_y, eta_text = [], [], []
    arr_x, arr_y, arr_text = [], [], []
    delay_x, delay_y, wait_x, wait_y = [], [], [], []
    for i in sorted(plan):
        ship = inst.ships[i]
        start, pos = plan[i]
        end = start + ship.handling_time
        cy = pos + ship.length / 2
        color = C.PRIORITY_COLORS.get(ship.priority, "#888888")
        arrival, eta = arrivals[i], ship.arrival
        fig.add_shape(type="rect", x0=start, x1=end, y0=pos, y1=pos + ship.length, fillcolor=color, opacity=0.78,
                      line=dict(color="white", width=1), layer="below")
        label_x.append((start + end) / 2)
        label_y.append(cy)
        label_text.append(str(i + 1))
        hx, hy = _hover_points(start, end, pos, pos + ship.length)
        hover_x += hx
        hover_y += hy
        text = (f"<b>{ship.name}</b> ({ship.priority}, Gewicht {ship.weight:g})<br>"
                f"Fahrplan-Ankunft: {eta} h &nbsp;|&nbsp; tatsächliche Ankunft: {arrival} h (Verspätung {arrival - eta} h)<br>"
                f"Anlegebeginn: {start} h &nbsp;|&nbsp; Wartezeit: {start - arrival} h<br>"
                f"Liegezeit: {start}-{end} h<br>Position: {pos}-{pos + ship.length} m &nbsp;|&nbsp; Tiefgang: {ship.draft} m")
        hover_text += [text] * len(hx)
        arr_x.append(arrival)
        arr_y.append(cy)
        arr_text.append(f"{ship.name}: tatsächliche Ankunft {arrival} h")
        if arrival > eta:
            eta_x.append(eta)
            eta_y.append(cy)
            eta_text.append(f"{ship.name}: Fahrplan-Ankunft {eta} h")
            delay_x += [eta, arrival, None]
            delay_y += [cy, cy, None]
        if start > arrival:
            wait_x += [arrival, start, None]
            wait_y += [cy, cy, None]

    fig.add_trace(go.Scatter(x=hover_x, y=hover_y, mode="markers", marker=dict(size=14, opacity=0), showlegend=False,
                             text=hover_text, hovertemplate="%{text}<extra></extra>", name="Schiffe"))
    fig.add_trace(go.Scatter(x=label_x, y=label_y, mode="text", text=label_text, textfont=dict(color="white", size=11),
                             showlegend=False, hoverinfo="skip", name="Schiffsnummern"))
    fig.add_trace(go.Scatter(x=wait_x, y=wait_y, mode="lines", line=dict(color=C.MARKER_LINE_COLOR, width=1.5, dash="dot"),
                             name="Wartezeit", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=delay_x, y=delay_y, mode="lines", line=dict(color=C.ETA_COLOR, width=2), name="Verspätung",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=eta_x, y=eta_y, mode="markers", name="Fahrplan-Ankunft ▽", text=eta_text, hovertemplate="%{text}<extra></extra>",
                             marker=dict(symbol="triangle-down-open", size=10, color=C.ETA_COLOR, line=dict(color=C.ETA_COLOR, width=2))))
    fig.add_trace(go.Scatter(x=arr_x, y=arr_y, mode="markers", name="tatsächliche Ankunft ◆", text=arr_text, hovertemplate="%{text}<extra></extra>",
                             marker=dict(symbol="diamond", size=8, color=C.ETA_COLOR, line=dict(color=C.MARKER_LINE_COLOR, width=1))))
    present = {inst.ships[i].priority for i in plan}
    for priority in C.PRIORITIES:
        if priority in present:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=priority,
                                     marker=dict(size=14, symbol="square", color=C.PRIORITY_COLORS[priority])))
    fig.update_layout(title=dict(text=title, y=0.98, yanchor="top") if title else None, xaxis_title="Zeit (Stunden)", yaxis_title="Kai-Position (Meter)",
                      template="plotly_white", height=C.CHART_HEIGHT + 60, legend=LEGEND_TOP, margin=dict(t=110 if title else 70), hovermode="closest")
    fig.update_xaxes(range=[0, t_end])
    fig.update_yaxes(range=[0, inst.quay_length])
    return _lock_axes(fig)


# ---------------------------------------------------------------------------------------------------
# Kostenkurve über die mittlere Verspätung
# ---------------------------------------------------------------------------------------------------
def cost_curve_figure(sweep, delay_current, tipping=None):
    """Gewichtete Wartezeit je Schiff über die mittlere Verspätung; Band = ± 1 Standardfehler; gepunktet = eingestellt, gestrichelt rot = Kipppunkt des Puffers."""
    import plotly.graph_objects as go

    fig = go.Figure()
    xs = list(sweep.deltas)
    for key in C.STRATEGY_KEYS:
        if key not in sweep.values:
            continue
        color, label = C.STRATEGY_COLORS[key], C.STRATEGY_LABELS[key]
        means = [sweep.mean(key, i) for i in range(len(xs))]
        sems = [sweep.sem(key, i) for i in range(len(xs))]
        upper = [m + e for m, e in zip(means, sems)]
        lower = [m - e for m, e in zip(means, sems)]
        fig.add_trace(go.Scatter(x=xs + xs[::-1], y=upper + lower[::-1], fill="toself", fillcolor=color, opacity=0.15, line=dict(width=0),
                                 hoverinfo="skip", showlegend=False, name=f"{label} (Band)"))
        fig.add_trace(go.Scatter(
            x=xs, y=means, mode="lines+markers", name=label, line=dict(color=color, width=2.5, dash=C.STRATEGY_DASH.get(key, "solid")),
            marker=dict(size=6), hovertemplate=f"<b>{label}</b><br>mittlere Verspätung %{{x}} h<br>%{{y:.2f}} h Wartezeit je Schiff<extra></extra>"))
    fig.add_vline(x=delay_current, line=dict(color=C.MARKER_LINE_COLOR, width=2, dash="dot"), annotation_text="eingestellt",
                  annotation_position="top", annotation_font=dict(size=11))
    if tipping is not None and 0 < tipping <= xs[-1]:
        fig.add_vline(x=tipping, line=dict(color="#c0392b", width=2, dash="dash"), annotation_text=f"Puffer lohnt ab ≈ {tipping:.1f} h",
                      annotation_position="bottom right", annotation_font=dict(size=12, color="#c0392b"))
    fig.update_layout(template="plotly_white", height=C.CHART_HEIGHT + 40, legend=LEGEND_BOTTOM, margin=dict(t=30, b=120),
                      xaxis_title="mittlere Verspätung der Schiffe (Stunden)", yaxis_title="gewichtete Wartezeit je Schiff (h)", hovermode="closest")
    fig.update_yaxes(rangemode="tozero")
    return _lock_axes(fig)


# ---------------------------------------------------------------------------------------------------
# Verteilung der Gewinne
# ---------------------------------------------------------------------------------------------------
def distribution_figure(dists):
    """Je Strategie ein gestapelter Balken: Anteil der Szenarien, in denen sie gegen die Referenz besser / gleich / schlechter abschneidet."""
    import plotly.graph_objects as go

    labels = [C.STRATEGY_SHORT[d.key].replace("<br>", " ") for d in dists]
    fig = go.Figure()
    for attr, name in (("better", "besser als starr"), ("equal", "gleich"), ("worse", "schlechter als starr")):
        shares = [getattr(d, attr) * 100 for d in dists]
        fig.add_trace(go.Bar(y=labels, x=shares, orientation="h", name=name, marker_color=C.OUTCOME_COLORS[attr],
                             text=[f"{v:.0f} %" if v >= 6 else "" for v in shares], textposition="inside", insidetextanchor="middle",
                             hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x:.0f}} % der Szenarien<extra></extra>"))
    fig.update_layout(barmode="stack", template="plotly_white", height=110 + 70 * len(dists), legend=dict(LEGEND_BOTTOM, traceorder="normal"),
                      margin=dict(t=20, b=90, l=10), xaxis_title="Anteil der Szenarien (%)")
    fig.update_xaxes(range=[0, 100])
    fig.update_yaxes(autorange="reversed")
    return _lock_axes(fig)


def gain_figure(dists):
    """Median-Gewinn neben Mittel-Gewinn je Strategie (Gesamtkosten je Szenario): ist der Mittelwert viel größer, tragen wenige Szenarien den Gewinn."""
    import plotly.graph_objects as go

    labels = [C.STRATEGY_SHORT[d.key] for d in dists]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=[d.median_gain for d in dists], name="Median (typisches Szenario)", marker_color="#2a6fb0",
                         hovertemplate="<b>%{x}</b><br>Median-Gewinn %{y:.1f} h<extra></extra>"))
    fig.add_trace(go.Bar(x=labels, y=[d.mean_gain for d in dists], name="Mittelwert", marker_color="#c77700",
                         hovertemplate="<b>%{x}</b><br>Mittel-Gewinn %{y:.1f} h<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=C.MARKER_LINE_COLOR, width=1))
    fig.update_layout(barmode="group", template="plotly_white", height=C.CHART_HEIGHT - 60, legend=LEGEND_BOTTOM, margin=dict(t=20, b=100),
                      yaxis_title="Gewinn gegen starr (h je Szenario)")
    return _lock_axes(fig)


# ---------------------------------------------------------------------------------------------------
# Vergleich der Strategien in einem Szenario
# ---------------------------------------------------------------------------------------------------
def comparison_figure(outcomes):
    """Zwei Blicke auf dasselbe Szenario: gewichtete Wartezeit gesamt je Strategie, und die mittlere Wartezeit je Prioritätsklasse."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=2, subplot_titles=("Gewichtete Wartezeit gesamt (h)", "Ø Wartezeit je Klasse (h)"), horizontal_spacing=0.12)
    labels = [C.STRATEGY_SHORT[o.key] for o in outcomes]
    fig.add_trace(go.Bar(x=labels, y=[o.wait_total for o in outcomes], marker_color=[C.STRATEGY_COLORS[o.key] for o in outcomes],
                         showlegend=False, hovertemplate="<b>%{x}</b><br>%{y:.1f} h<extra></extra>"), row=1, col=1)
    for o in outcomes:
        fig.add_trace(go.Bar(x=list(C.PRIORITIES), y=[o.wait_by_priority.get(p, 0.0) for p in C.PRIORITIES], name=o.label,
                             marker_color=C.STRATEGY_COLORS[o.key], hovertemplate=f"<b>{o.label}</b><br>%{{x}}: %{{y:.1f}} h<extra></extra>"),
                      row=1, col=2)
    fig.update_layout(barmode="group", template="plotly_white", height=C.CHART_HEIGHT, legend=LEGEND_BOTTOM, margin=dict(t=40, b=120))
    fig.update_xaxes(tickangle=0, tickfont=dict(size=10), row=1, col=1)
    return _lock_axes(fig)
