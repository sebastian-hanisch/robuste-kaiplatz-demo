"""Ausführung eines Kaiplans unter Verspätungen: drei Strategien, dieselben Verspätungen (gepaart).

  starr        Plan auf den Fahrplan-Ankünften; bei Verspätung Rechts-Verschiebung: Positionen und räumliche Reihenfolge bleiben,
               Anlegebeginn = max(tatsächliche Ankunft, geplantes Fenster, Ende aller räumlich überlappenden Vorgänger).
  puffer b     Plan mit um b Stunden verlängerter Belegung je Schiff (Lücken), Ausführung wie starr mit den echten Liegezeiten.
  neuplanung   bei jeder Ankunft und wenn ein geplantes Fenster ohne Schiff verstreicht werden alle noch nicht liegenden Schiffe neu
               eingeplant; liegende Schiffe sind feste Hindernisse; noch nicht angekommene Schiffe zählen ab max(ETA, jetzt + r).
               r = 1 heißt: nur die ETA, keine Prognose. r > 1 ist die erwartete Restverspätung (Prognose).
Kosten: Σ Gewicht · (Anlegebeginn − tatsächliche Ankunft), die Wartezeit zählt ab der TATSÄCHLICHEN Ankunft."""

import dataclasses
import random
from dataclasses import dataclass, field

import rb_constants as C
from berth_heuristic import _insert, greedy_and_polish
from rb_delays import actual_arrivals, buffered_instance


@dataclass(frozen=True)
class Execution:
    """Ergebnis einer Ausführung. starts/positions: tatsächlicher Anlegebeginn und Kaiposition je Schiff (Index -> Wert).
    announced: der zu Beginn angekündigte Plan (Index -> (Start, Position)); replans: Anzahl Neuplanungen (0 bei starr/Puffer)."""
    starts: dict
    positions: dict
    announced: dict
    replans: int = 0
    arrivals: dict = field(default_factory=dict)

    @property
    def plan(self):
        return {i: (self.starts[i], self.positions[i]) for i in self.starts}

    def position_changes(self):
        """Anzahl Schiffe, die am Ende an einer anderen Kaiposition liegen als zu Beginn angekündigt."""
        return sum(1 for i in self.positions if self.positions[i] != self.announced[i][1])

    def window_shift(self):
        """Mittlere absolute Abweichung des tatsächlichen Anlegebeginns vom angekündigten, in Stunden."""
        return sum(abs(self.starts[i] - self.announced[i][0]) for i in self.starts) / len(self.starts)


def weighted_wait(inst, starts, arrivals):
    """Σ Gewicht · (Anlegebeginn − tatsächliche Ankunft)."""
    return sum(s.weight * (starts[s.index] - arrivals[s.index]) for s in inst.ships)


def wait_per_ship(inst, ex):
    return weighted_wait(inst, ex.starts, ex.arrivals) / len(inst.ships)


# ---------------- starr und Puffer ----------------
def plan_on_etas(inst, max_moves=C.STATIC_PLAN_MAX_MOVES, seed=0):
    """Startplan auf den Fahrplan-Ankünften (Einfüge-Heuristik + lokale Suche), Index -> (Start, Position)."""
    return greedy_and_polish(inst, seed=seed, max_moves=max_moves)


def _space_overlap(inst, plan, i, j):
    pi, pj = plan[i][1], plan[j][1]
    wi, wj = inst.occupied_width(inst.ships[i]), inst.occupied_width(inst.ships[j])
    return pi < pj + wj and pj < pi + wi


def right_shift(inst, plan, arrivals):
    """Rechts-Verschiebung eines Plans auf die tatsächlichen Ankünfte; `inst` trägt die echten Liegezeiten. Gibt Index -> Anlegebeginn zurück."""
    order = sorted(plan, key=lambda i: (plan[i][0], i))
    starts, ends = {}, {}
    for k, i in enumerate(order):
        s = max(arrivals[i], plan[i][0])
        for j in order[:k]:
            if _space_overlap(inst, plan, i, j):
                s = max(s, ends[j])
        starts[i] = s
        ends[i] = s + inst.ships[i].handling_time
    return starts


def run_static(inst, delays, plan=None, buffer_h=0):
    """Starre Ausführung. `plan` (auf den ETAs, ggf. mit Puffer geplant) darf vorgegeben werden, sonst wird er berechnet."""
    if plan is None:
        plan = plan_on_etas(buffered_instance(inst, buffer_h) if buffer_h else inst)
    arrivals = actual_arrivals(inst, delays)
    starts = right_shift(inst, plan, arrivals)
    return Execution(starts=starts, positions={i: plan[i][1] for i in plan}, announced=dict(plan), replans=0, arrivals=arrivals)


# ---------------- Neuplanung ----------------
def _build_fixed(inst, fixed, order):
    plan = dict(fixed)
    for i in order:
        plan[i] = _insert(inst, plan, inst.ships[i])
    return plan


def _score_remaining(inst, fixed, order):
    plan = _build_fixed(inst, fixed, order)
    return sum(inst.ships[i].weight * (plan[i][0] - inst.ships[i].arrival) for i in order), plan


def replan(inst_eff, fixed, remaining, max_moves=C.REPLAN_MAX_MOVES):
    """Referenz-Neuplanung: Plan für die noch nicht liegenden Schiffe `remaining` mit Hindernissen `fixed` (Index -> (Start, Position)).
    Einfüge-Heuristik aus zwei Startreihenfolgen (Ankunft; Gewicht) und Tausch-Suche über die Einfüge-Reihenfolge."""
    cands = [sorted(remaining, key=lambda i: (inst_eff.ships[i].arrival, i)),
             sorted(remaining, key=lambda i: (-inst_eff.ships[i].weight, inst_eff.ships[i].arrival, i))]
    scored = [(_score_remaining(inst_eff, fixed, o)[0], o) for o in cands]
    best_score, best_order = min(scored, key=lambda x: x[0])
    rng = random.Random(0)
    moves, improved, n = 0, True, len(best_order)
    while improved and moves < max_moves and n > 1:
        improved = False
        pairs = [(a, b) for a in range(n) for b in range(a + 1, n)]
        rng.shuffle(pairs)
        for a, b in pairs:
            if moves >= max_moves:
                break
            moves += 1
            cand = list(best_order)
            cand[a], cand[b] = cand[b], cand[a]
            sc = _score_remaining(inst_eff, fixed, cand)[0]
            if sc < best_score - 1e-9:
                best_order, best_score, improved = cand, sc, True
    return _score_remaining(inst_eff, fixed, best_order)[1]


def replan_fast(inst_eff, fixed, remaining, max_moves=C.REPLAN_MAX_MOVES):
    """Wie `replan`, aber billiger bei IDENTISCHEM Ergebnis: (1) der unveränderte Anfang der Reihenfolge wird wiederverwendet (Einfügen ist
    sequentiell: ein Tausch (a, b) ändert erst ab Position a etwas), (2) ein Tausch wird abgebrochen, sobald die Teilkosten schon nicht mehr
    besser als die beste Reihenfolge sein können (Kosten wachsen beim Einfügen nur)."""
    ships = inst_eff.ships

    def place(plan, order_tail, cost0, limit):
        c = cost0
        for i in order_tail:
            plan[i] = _insert(inst_eff, plan, ships[i])
            c += ships[i].weight * (plan[i][0] - ships[i].arrival)
            if c >= limit:
                return None
        return c

    def build_all(order):
        plans, costs = [dict(fixed)], [0.0]
        for i in order:
            pl = dict(plans[-1])
            plans.append(pl)
            costs.append(place(pl, [i], costs[-1], float("inf")))
        return plans, costs

    cands = [sorted(remaining, key=lambda i: (ships[i].arrival, i)),
             sorted(remaining, key=lambda i: (-ships[i].weight, ships[i].arrival, i))]
    built = [(build_all(o), o) for o in cands]
    (best_plans, best_costs), best_order = min(built, key=lambda x: x[0][1][-1])
    rng = random.Random(0)
    moves, improved, n = 0, True, len(best_order)
    while improved and moves < max_moves and n > 1:
        improved = False
        pairs = [(a, b) for a in range(n) for b in range(a + 1, n)]
        rng.shuffle(pairs)
        for a, b in pairs:
            if moves >= max_moves:
                break
            moves += 1
            cand = list(best_order)
            cand[a], cand[b] = cand[b], cand[a]
            pl = dict(best_plans[a])
            c = place(pl, cand[a:], best_costs[a], best_costs[-1] - 1e-9)
            if c is not None and c < best_costs[-1] - 1e-9:
                best_order = cand
                best_plans, best_costs = build_all(cand)      # exakt neu aufbauen (einfach und sicher)
                improved = True
    return best_plans[-1]


def run_reactive(inst, delays, expected_delay=1, max_moves=C.REPLAN_MAX_MOVES, replanner=replan_fast):
    """Stundenweise Ereignissimulation der Neuplanung. Bekannt zur Zeit tau: alle Schiffe mit tatsächlicher Ankunft <= tau.
    `expected_delay` (r >= 1): noch nicht angekommene Schiffe werden ab max(ETA, tau + r) eingeplant; r = 1 ist "nur die ETA" (keine Prognose).
    `replanner(inst_eff, fixed, remaining, max_moves)` ist austauschbar (Tests prüfen darüber die Invarianten je Ereignis)."""
    if expected_delay < 1:
        raise ValueError("expected_delay muss >= 1 sein (ein noch nicht angekommenes Schiff kommt frühestens in der nächsten Stunde)")
    arrivals = actual_arrivals(inst, delays)
    started, remaining = {}, set(range(len(inst.ships)))
    plan_rem, announced, replans, tau, last_arrival = {}, None, 0, 0, max(arrivals.values(), default=0)
    while remaining:
        if tau > (inst.horizon + last_arrival) * 3:
            raise RuntimeError("Simulation läuft nicht aus")
        newly = any(arrivals[i] == tau for i in remaining)
        overdue = any(arrivals[i] > tau and plan_rem[i][0] <= tau for i in remaining if i in plan_rem)
        if tau == 0 or newly or overdue or any(i not in plan_rem for i in remaining):
            eff = tuple(
                dataclasses.replace(s, arrival=(max(arrivals[s.index], tau) if arrivals[s.index] <= tau
                                                else max(s.arrival, tau + expected_delay)))
                if s.index in remaining else s
                for s in inst.ships)
            plan = replanner(dataclasses.replace(inst, ships=eff), dict(started), sorted(remaining), max_moves)
            plan_rem = {i: plan[i] for i in remaining}
            if announced is None:
                announced = {i: plan[i] for i in range(len(inst.ships))}
            replans += 1
        for i in sorted(remaining):
            if plan_rem[i][0] <= tau and arrivals[i] <= tau:
                started[i] = (tau, plan_rem[i][1])
                remaining.discard(i)
        tau += 1
    return Execution(starts={i: started[i][0] for i in started}, positions={i: started[i][1] for i in started},
                     announced=announced, replans=replans, arrivals=arrivals)
