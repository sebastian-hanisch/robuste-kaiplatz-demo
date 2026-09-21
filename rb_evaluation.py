"""Auswertung: ein Szenario mit allen Strategien, Kostenkurve über die Verspätung, gepaarte Differenz, Verteilung besser/gleich/schlechter,
Kipppunkt des Puffers, Urteil, Kennzahlen.

Reine Rechnung ohne Streamlit; app.py legt die teuren Teile (`delay_sweep`, `solve_clairvoyant`) per st.cache_data ab.
Alle Kosten sind gewichtete Wartestunden ab TATSÄCHLICHER Ankunft; "Gewinn" heißt Kosten der Referenz (starr) minus Kosten der Strategie,
positiv = die Strategie ist besser."""

import math
import statistics
from dataclasses import dataclass

import rb_constants as C
from rb_delays import scenario_delays
from rb_exact import solve_clairvoyant
from rb_execution import plan_on_etas, run_reactive, run_static, weighted_wait
from rb_delays import buffered_instance
from rb_scenario import is_playable, make_instance


def forecast_hours(delay_mean, forecast_pct):
    """Erwartete Restverspätung r (ganze Stunden, >= 1) der Prognose-Strategie: forecast_pct % der mittleren Verspätung; 0 % heißt r = 1 (nur ETA)."""
    return max(1, round(delay_mean * forecast_pct / 100))


# ---------------------------------------------------------------------------------------------------
# Ein Szenario, alle Strategien
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class StrategyOutcome:
    key: str
    label: str
    execution: object           # rb_execution.Execution
    wait_total: float           # gewichtete Wartestunden gesamt
    wait_per_ship: float
    wait_by_priority: dict      # Priorität -> mittlere (ungewichtete) Wartezeit in Stunden

    @property
    def replans(self):
        return self.execution.replans

    @property
    def position_changes(self):
        return self.execution.position_changes()

    @property
    def window_shift(self):
        return self.execution.window_shift()


def static_plans(inst, buffer_h):
    """Die beiden Pläne auf den Fahrplan-Ankünften: ohne und mit Puffer. Unabhängig von den Verspätungen, also je Instanz einmal zu rechnen."""
    return plan_on_etas(inst), plan_on_etas(buffered_instance(inst, buffer_h)) if buffer_h else None


def _outcome(inst, key, ex):
    total = weighted_wait(inst, ex.starts, ex.arrivals)
    by_prio = {}
    for s in inst.ships:
        by_prio.setdefault(s.priority, []).append(ex.starts[s.index] - ex.arrivals[s.index])
    return StrategyOutcome(key, C.STRATEGY_LABELS[key], ex, total, total / len(inst.ships),
                           {p: statistics.fmean(v) for p, v in by_prio.items()})


def run_strategies(inst, delays, delay_mean, buffer_h, forecast_pct, plans=None):
    """Starr, Puffer, Neuplanung und Neuplanung + Prognose auf DEMSELBEN Szenario (gleiche Verspätungen). Hellsehen kommt getrennt (rb_exact)."""
    plain, buffered = plans if plans is not None else static_plans(inst, buffer_h)
    runs = {
        C.STRAT_STARR: run_static(inst, delays, plan=plain),
        C.STRAT_PUFFER: run_static(inst, delays, plan=buffered if buffer_h else plain),
        C.STRAT_NEU: run_reactive(inst, delays, 1),
        C.STRAT_PROGNOSE: run_reactive(inst, delays, forecast_hours(delay_mean, forecast_pct)),
    }
    return tuple(_outcome(inst, key, ex) for key, ex in runs.items())


def outcome_of(outcomes, key):
    return next(o for o in outcomes if o.key == key)


@dataclass(frozen=True)
class Row:
    key: str
    label: str
    wait_total: float
    wait_per_ship: float
    wait_by_priority: dict
    replans: int
    position_changes: int
    delta_vs_baseline: float        # meine minus Referenz (negativ = besser), Gesamtkosten
    delta_pct: float | None         # in % der Referenz; None, wenn die Referenz 0 kostet


def comparison_rows(outcomes, baseline=C.BASELINE):
    ref = outcome_of(outcomes, baseline).wait_total
    return tuple(Row(o.key, o.label, o.wait_total, o.wait_per_ship, o.wait_by_priority, o.replans, o.position_changes,
                     o.wait_total - ref, 100.0 * (o.wait_total - ref) / ref if ref else None) for o in outcomes)


# ---------------------------------------------------------------------------------------------------
# Kostenkurve über die mittlere Verspätung
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SweepResult:
    deltas: tuple               # aufsteigend
    kind: str                   # Verspätungsart
    n_ships: int
    n_scenarios: int            # Szenarien je Verspätung (Instanzen x Ziehungen)
    values: dict                # Strategie -> Tupel über delta von Tupeln über Szenarien: gewichtete Wartestunden gesamt (ohne Hellsehen ggf. ohne diesen Schlüssel)
    unproven: int               # Hellsehen-Lösungen im ganzen Sweep, die im Zeitlimit nicht bewiesen wurden

    def index_of(self, delta):
        return min(range(len(self.deltas)), key=lambda i: abs(self.deltas[i] - delta))

    def series(self, key, i):
        return self.values[key][i]

    def mean(self, key, i):
        """Mittelwert der Kosten JE SCHIFF."""
        return statistics.fmean(self.series(key, i)) / self.n_ships

    def sem(self, key, i):
        v = self.series(key, i)
        return statistics.stdev(v) / math.sqrt(len(v)) / self.n_ships if len(v) > 1 else 0.0

    def gains(self, key, i, baseline=C.BASELINE):
        """Gewinn je Szenario gegenüber der Referenz (Gesamtkosten): Referenz minus Strategie, positiv = besser."""
        return tuple(b - s for b, s in zip(self.series(baseline, i), self.series(key, i)))

    def paired_diff(self, key, baseline, i):
        """(Mittel, Standardfehler) von key - baseline je Schiff über dieselben Szenarien; negativ = key besser."""
        d = [(x - y) / self.n_ships for x, y in zip(self.series(key, i), self.series(baseline, i))]
        return statistics.fmean(d), (statistics.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else 0.0)


def sweep_instances(n_ships, quay_length, arrival_spread, handling_avg, mainliner_fraction, n_instances):
    """Die Instanzen der Kurve: Seeds 0, 1, 2, ... (unabhängig vom eingestellten Seed), nur spielbare; begrenzt suchen."""
    out, seed = [], 0
    while len(out) < n_instances and seed < 20 * n_instances + 20:
        inst = make_instance(n_ships, quay_length, arrival_spread, handling_avg, mainliner_fraction, seed)
        if is_playable(inst):
            out.append(inst)
        seed += 1
    if len(out) < n_instances:
        raise ValueError("kaum eine spielbare Instanz mit diesen Einstellungen (Schiffe passen nicht an den Kai)")
    return out


def draw_seed(instance_index, draw_index):
    """Verspätungs-Seed eines Szenarios der Kurve; für alle Verspätungen gleich (gemeinsame Zufallszahlen: die Kurve ist glatter und die Strategien gepaart)."""
    return 1000 * instance_index + draw_index


def delay_sweep(n_ships, quay_length, arrival_spread, handling_avg, mainliner_fraction, delay_kind, delay_current,
                buffer_h, forecast_pct, n_instances=C.SWEEP_INSTANCES, n_draws=C.SWEEP_DRAWS, deltas=C.SWEEP_DELTAS,
                with_exact=True, exact_time_limit=C.SWEEP_EXACT_TIME_LIMIT_SECONDS, progress=None):
    """Kosten der Strategien über die mittlere Verspätung für die eingestellte Hafengröße und Verspätungsart. Mit `with_exact` (Vorgabe) kommt
    das Hellsehen dazu, sonst nur die vier ausführbaren Strategien. Das eingestellte delay gehört immer zum Raster. Die Instanzen und Ziehungen
    hängen nur von ihrer Nummer ab, eine größere Stichprobe enthält also die kleinere.
    `progress(anteil)` wird nach jedem Szenario mit einem Wert in (0, 1] aufgerufen (Fortschrittsbalken)."""
    grid = tuple(sorted(set(deltas) | {delay_current}))
    insts = sweep_instances(n_ships, quay_length, arrival_spread, handling_avg, mainliner_fraction, n_instances)
    plans = [static_plans(inst, buffer_h) for inst in insts]
    keys = C.STRATEGY_KEYS if with_exact else tuple(k for k in C.STRATEGY_KEYS if k != C.STRAT_EXACT)
    values = {k: [[] for _ in grid] for k in keys}
    unproven, done, total = 0, 0, len(grid) * len(insts) * n_draws
    for gi, delta in enumerate(grid):
        for k, inst in enumerate(insts):
            for j in range(n_draws):
                d = scenario_delays(inst, delta, delay_kind, draw_seed(k, j))
                for o in run_strategies(inst, d, delta, buffer_h, forecast_pct, plans[k]):
                    values[o.key][gi].append(o.wait_total)
                if with_exact:
                    ex = solve_clairvoyant(inst, d, exact_time_limit)
                    unproven += not ex.proven
                    values[C.STRAT_EXACT][gi].append(ex.weighted_wait)
                done += 1
                if progress:
                    progress(done / total)
    return SweepResult(grid, delay_kind, n_ships, len(insts) * n_draws,
                       {k: tuple(tuple(v) for v in vs) for k, vs in values.items()}, unproven)


# ---------------------------------------------------------------------------------------------------
# Kennzahlen, Verteilung, Kipppunkt, Urteil
# ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Distribution:
    key: str
    better: float               # Anteile der Szenarien (0..1), gegen die Referenz
    equal: float
    worse: float
    mean_gain: float            # Gesamtkosten je Szenario
    median_gain: float
    p90_gain: float
    top10_share: float | None   # Anteil des gesamten positiven Gewinns, der aus den besten 10 % der Szenarien kommt; None ohne positiven Gewinn


def distribution(sweep, key, delay, baseline=C.BASELINE, tol=C.TIE_TOLERANCE):
    """Wie sich die Gewinne über die Szenarien verteilen: Mittelwerte täuschen bei schiefer Verteilung (Median << Mittel, Verluste im Einzelfall)."""
    g = sweep.gains(key, sweep.index_of(delay), baseline)
    n = len(g)
    better = sum(1 for x in g if x > tol)
    worse = sum(1 for x in g if x < -tol)
    ranked = sorted(g)
    top = sorted(g, reverse=True)[: max(1, n // 10)]
    positive = sum(x for x in g if x > 0)
    return Distribution(key, better / n, (n - better - worse) / n, worse / n, statistics.fmean(g), statistics.median(g),
                        ranked[min(n - 1, int(0.9 * n))], sum(x for x in top if x > 0) / positive if positive else None)


def buffer_tipping_point(sweep):
    """Mittlere Verspätung, ab der der Puffer im Mittel besser ist als der starre Plan (lineare Interpolation des ersten Vorzeichenwechsels
    von Puffer minus starr auf dem Raster, das mit delay 0 beginnen muss). 0.0, wenn er schon ohne Verspätung nicht schlechter ist; None, wenn
    er im ganzen Raster schlechter bleibt."""
    if sweep.deltas[0] != 0:
        raise ValueError("der Kipppunkt braucht ein Raster, das bei 0 beginnt")
    diffs = [sweep.mean(C.STRAT_PUFFER, i) - sweep.mean(C.STRAT_STARR, i) for i in range(len(sweep.deltas))]
    if diffs[0] <= 0:
        return 0.0
    for i in range(len(diffs) - 1):
        if diffs[i] > 0 >= diffs[i + 1]:
            d0, d1 = sweep.deltas[i], sweep.deltas[i + 1]
            return d0 + (d1 - d0) * diffs[i] / (diffs[i] - diffs[i + 1])
    return None


@dataclass(frozen=True)
class Verdict:
    kind: str                   # "better" | "worse" | "unclear"
    diff: float                 # Strategie minus Referenz, je Schiff (negativ = besser)
    se: float                   # Standardfehler der gepaarten Differenz
    pct: float | None           # Unterschied in % der Referenz (negativ = besser)
    loss_share: float           # Anteil der Szenarien, in denen die Strategie schlechter als die Referenz ist


def verdict(sweep, key, delay, baseline=C.BASELINE):
    """Bewertung einer Strategie gegen die Referenz beim eingestellten delay. 'Klar' heißt: Unterschied > VERDICT_Z Standardfehler der gepaarten
    Differenz; sonst 'unclear' - lieber kein Urteil als eines im Rauschen."""
    i = sweep.index_of(delay)
    diff, se = sweep.paired_diff(key, baseline, i)
    base = sweep.mean(baseline, i)
    kind = "unclear" if abs(diff) <= C.VERDICT_Z * se else ("better" if diff < 0 else "worse")
    return Verdict(kind, diff, se, 100.0 * diff / base if base else None, distribution(sweep, key, delay, baseline).worse)


@dataclass(frozen=True)
class KeyFigures:
    delay: float                        # das tatsächlich ausgewertete Raster-delay
    buffer_price_at_zero_pct: float | None   # Mehrkosten des Puffers gegenüber starr ohne Verspätung, in % (Kurve)
    reactive_gain: float                # Neuplanung: Gewinn je Schiff gegenüber starr beim eingestellten delay (positiv = besser; Fokus-Stichprobe)
    reactive_gain_pct: float | None
    forecast_gain: float
    forecast_gain_pct: float | None
    price_of_uncertainty: float         # starr minus Hellsehen je Schiff (Kurve)
    tipping_point: float | None         # siehe buffer_tipping_point (Kurve)


def key_figures(curve, focus, delay):
    """Kennzahlen: Pufferpreis, Kipppunkt und Preis der Unsicherheit aus der Kurve (nur dort gibt es das Hellsehen und das Verspätungsraster),
    die Gewinne der Neuplanung aus der größeren Fokus-Stichprobe beim eingestellten delay."""
    ic, i0, ifo = curve.index_of(delay), 0, focus.index_of(delay)
    pct = lambda gain, ref: 100.0 * gain / ref if ref else None
    base0 = curve.mean(C.STRAT_STARR, i0)
    puffer0 = curve.mean(C.STRAT_PUFFER, i0) - base0
    base = focus.mean(C.STRAT_STARR, ifo)
    neu = base - focus.mean(C.STRAT_NEU, ifo)
    prog = base - focus.mean(C.STRAT_PROGNOSE, ifo)
    return KeyFigures(curve.deltas[ic], pct(puffer0, base0), neu, pct(neu, base), prog, pct(prog, base),
                      curve.mean(C.STRAT_STARR, ic) - curve.mean(C.STRAT_EXACT, ic), buffer_tipping_point(curve))
