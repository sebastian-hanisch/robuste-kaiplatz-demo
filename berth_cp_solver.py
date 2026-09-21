"""Exakter Referenzlöser (Google OR-Tools CP-SAT) für die Kaiplatz-Zuteilung.

Modell: jedes Schiff bekommt eine Startzeit `start[i]` (Domäne ab seiner Ankunft) und eine
Kai-Position `pos[i]` (Domäne = Vereinigung der tiefgang-kompatiblen Zonen, in denen das Schiff
mit Sicherheitsabstand überhaupt passt). Zwei Intervall-Variablen je Schiff - eine in der Zeit
(Dauer = feste Liegezeit), eine im Raum (Breite = Länge + Sicherheitsabstand) - und EIN
`AddNoOverlap2D`-Aufruf über alle Schiffe erzwingt, dass sich keine zwei Rechtecke im
Zeit-Position-Raum überlappen. Das ersetzt die von Hand geschriebenen paarweisen
Reihenfolge-Constraints, die quaycrane_cp_solver.py für ein ganz ähnlich klingendes Problem
braucht (dort zusätzlich erschwert durch Kran-Interferenz WÄHREND der Fahrt zwischen Aufgaben,
siehe [[project_quaycrane_demo_venv]]) - hier gibt es keine Fahrt zwischen Positionen und keine
Reihenfolge auf einer gemeinsamen Schiene, nur reine Rechteck-Nichtüberlappung.

Da Länge, Tiefgang-Grenzen, Ankunft und Liegezeit hier bereits als Ganzzahlen (Meter, Stunden)
erzeugt werden (siehe berth_scenario.py), braucht dieses Modell - anders als quaycrane_cp_solver.py
- KEINE Skalierung und damit auch keine Rundungsfehler zwischen stetiger und diskreter Welt.

Minimiert wird primär die gewichtete Wartezeit (Prioritätsgewicht × Wartezeit je Schiff), als
lexikografisches Tie-Breaking-Ziel zusätzlich die unge­wichtete Gesamtwartezeit - ohne dieses
zweite Ziel kann der Solver unter mehreren gleich guten Lösungen eine mit unnötiger Wartezeit
auf einem Schiff zurückgeben, obwohl eine Lösung mit demselben gewichteten Wert existiert, bei
der niemand unnötig wartet (siehe [[feedback_cp_sat_lexicographic_tiebreak]])."""

import os
import time
from dataclasses import dataclass

from ortools.sat.python import cp_model

WEIGHT_SCALE = 2  # macht die Prioritätsgewichte (1.0/1.5/3.0) ganzzahlig (2/3/6)

NUM_SEARCH_WORKERS = min(8, os.cpu_count() or 1)  # siehe quaycrane_cp_solver.py-Fund: 2-Kern-CI
# reagiert schlecht auf mehr Suchpfade, als es echte Kerne gibt.


def build_model(instance):
    """Baut das reine Constraint-Modell (ohne Zielfunktion/Hints/Solver-Aufruf) - eigenständig
    aufrufbar für Tests, die gezielt Variablen fixieren und Machbarkeit isoliert prüfen wollen.
    Setzt voraus, dass `instance.is_trivially_infeasible()` bereits als False geprüft wurde -
    sonst hätte mindestens ein Schiff eine leere Positions-Domäne."""
    model = cp_model.CpModel()
    n = len(instance.ships)

    start = []
    pos = []
    time_intervals = []
    pos_intervals = []

    for ship in instance.ships:
        width = instance.occupied_width(ship)
        zone_ranges = [
            (z.start, z.end - width) for z in instance.compatible_zones(ship) if (z.end - z.start) >= width
        ]
        pos_domain = cp_model.Domain.FromIntervals([[lo, hi] for lo, hi in zone_ranges])

        s = model.NewIntVar(ship.arrival, instance.horizon, f"start_{ship.index}")
        p = model.NewIntVarFromDomain(pos_domain, f"pos_{ship.index}")
        start.append(s)
        pos.append(p)

        time_intervals.append(model.NewIntervalVar(s, ship.handling_time, s + ship.handling_time, f"time_{ship.index}"))
        pos_intervals.append(model.NewIntervalVar(p, width, p + width, f"space_{ship.index}"))

    if n > 1:
        model.AddNoOverlap2D(time_intervals, pos_intervals)

    return model, start, pos, n


@dataclass
class ExactResult:
    feasible: bool
    optimal: bool
    plan: dict
    total_weighted_wait: float
    wall_time_ms: float


def solve_exact(instance, time_limit_seconds=10, hint_plan=None):
    """hint_plan: optionaler bereits bekannter zulässiger Plan (z.B. von einer Heuristik, Format
    wie berth_heuristic._build's Rückgabe) - als CP-SAT-Hint übergeben, gibt dem Solver sofort
    einen gültigen Startpunkt statt bei null zu suchen."""
    t0 = time.perf_counter()
    model, start, pos, n = build_model(instance)

    waits = [start[i] - instance.ships[i].arrival for i in range(n)]
    weighted_terms = [round(instance.ships[i].weight * WEIGHT_SCALE) * waits[i] for i in range(n)]
    tie_break_weight = n * instance.horizon + 1
    model.Minimize(sum(weighted_terms) * tie_break_weight + sum(waits))

    if hint_plan:
        for i, ship in enumerate(instance.ships):
            hint_start, hint_pos = hint_plan[ship.index]
            model.AddHint(start[i], hint_start)
            model.AddHint(pos[i], hint_pos)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = NUM_SEARCH_WORKERS
    status = solver.Solve(model)
    wall_time_ms = (time.perf_counter() - t0) * 1000

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ExactResult(feasible=False, optimal=False, plan={}, total_weighted_wait=0.0, wall_time_ms=wall_time_ms)

    plan = {ship.index: (solver.Value(start[i]), solver.Value(pos[i])) for i, ship in enumerate(instance.ships)}
    total_weighted_wait = sum(instance.ships[i].weight * solver.Value(waits[i]) for i in range(n))

    return ExactResult(
        feasible=True,
        optimal=status == cp_model.OPTIMAL,
        plan=plan,
        total_weighted_wait=total_weighted_wait,
        wall_time_ms=wall_time_ms,
    )
