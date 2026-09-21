"""Hellsehen: der Kaiplan, den man bei Kenntnis ALLER tatsächlichen Ankünfte im Voraus wählen würde (CP-SAT der berth-allocation-demo).

Das ist die untere Schranke für jede Strategie, die nur ETAs und bisher eingetretene Ankünfte kennt; der Abstand einer Strategie zu diesem
Wert ist der "Preis der Unsicherheit". Er ist nicht erreichbar, sondern nur der Maßstab.

Ehrlichkeit bei Zeitlimit: wird das Optimum nicht bewiesen, ist der Wert nur eine OBERgrenze des Optimums (eine gefundene Lösung), der Preis der
Unsicherheit also womöglich zu klein. `Clairvoyant.proven` sagt, ob man dem Wert als Optimum trauen darf; die Oberfläche muss "nicht bewiesen" anzeigen."""

from dataclasses import dataclass

import rb_constants as C
from berth_cp_solver import solve_exact
from berth_evaluation import check_feasible
from berth_heuristic import greedy_and_polish
from rb_delays import actual_instance


@dataclass(frozen=True)
class Clairvoyant:
    """Ergebnis des Hellsehens. `proven`: Optimalität vom Löser bewiesen. `source`: "CP-SAT" oder "Heuristik" (Rückfall, falls der Löser im
    Zeitlimit gar keine Lösung fand; dann nie bewiesen). `weighted_wait`: Σ Gewicht · (Anlegebeginn − tatsächliche Ankunft)."""
    starts: dict
    positions: dict
    weighted_wait: float
    proven: bool
    source: str
    wall_time_ms: float

    @property
    def plan(self):
        return {i: (self.starts[i], self.positions[i]) for i in self.starts}


def _weighted_wait(inst_actual, plan):
    return sum(s.weight * (plan[s.index][0] - s.arrival) for s in inst_actual.ships)


def solve_clairvoyant(inst, delays, time_limit_seconds=C.EXACT_TIME_LIMIT_SECONDS):
    """CP-SAT auf der Instanz mit den tatsächlichen Ankünften. Die Einfüge-Heuristik liefert einen zulässigen Startplan als Hint (der Löser hat sofort
    eine Lösung) und den Rückfall, falls das Zeitlimit ohne Lösung abläuft."""
    real = actual_instance(inst, delays)
    hint = greedy_and_polish(real, seed=0, max_moves=C.STATIC_PLAN_MAX_MOVES)
    res = solve_exact(real, time_limit_seconds=time_limit_seconds, hint_plan=hint)
    if res.feasible:
        plan, proven, source = res.plan, res.optimal, "CP-SAT"
    else:
        plan, proven, source = hint, False, "Heuristik"
    ok, violations = check_feasible(real, plan)
    if not ok:
        raise RuntimeError(f"Hellsehen lieferte einen unzulässigen Plan: {violations[:2]}")
    return Clairvoyant(starts={i: plan[i][0] for i in plan}, positions={i: plan[i][1] for i in plan},
                       weighted_wait=_weighted_wait(real, plan), proven=proven, source=source, wall_time_ms=res.wall_time_ms)


def price_of_uncertainty(strategy_wait, exact):
    """Abstand einer Strategie zum Hellsehen (Gesamtkosten, >= 0 wenn `exact.proven`). Bei nicht bewiesenem Optimum kann die Strategie
    besser als die gefundene Lösung sein; dann wird 0 gemeldet (der wahre Preis ist unbekannt) - `exact.proven` gehört dann in die Anzeige."""
    gap = strategy_wait - exact.weighted_wait
    return gap if exact.proven else max(0.0, gap)
