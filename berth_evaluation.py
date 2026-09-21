"""Machbarkeitsprüfung und Kennzahlen - unabhängig davon, ob der Belegungsplan von einer
Heuristik oder vom CP-SAT-Löser stammt (`berth_heuristic.py` / `berth_cp_solver.py` nutzen
BEIDE ausschließlich diese Funktionen zur Prüfung, damit Konstruktion und Prüfung nie
auseinanderlaufen können - siehe [[project_quaycrane_demo_venv]] für die Geschichte, warum das
wichtig ist).

Ein Belegungsplan ist ein dict `ship_index -> (start, pos)` (Stunden, Meter)."""

from collections import defaultdict


def _intervals_overlap(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


def _zone_for_position(instance, pos):
    for z in instance.zones:
        if z.start <= pos < z.end or (pos == z.end == instance.quay_length):
            return z
    return None


def check_feasible(instance, plan):
    violations = []
    ships_by_index = {s.index: s for s in instance.ships}

    if set(plan.keys()) != set(ships_by_index.keys()):
        violations.append("Nicht jedes Schiff genau einmal eingeplant.")

    for idx, (start, pos) in plan.items():
        ship = ships_by_index[idx]
        if start < ship.arrival:
            violations.append(f"{ship.name}: Anlegebeginn {start}h liegt vor Ankunft {ship.arrival}h.")

        width = instance.occupied_width(ship)
        zone = _zone_for_position(instance, pos)
        if zone is None or pos + ship.length > zone.end or pos < zone.start:
            violations.append(f"{ship.name}: Position {pos}-{pos + ship.length}m liegt außerhalb einer Zone.")
        elif zone.max_draft < ship.draft:
            violations.append(
                f"{ship.name}: Tiefgang {ship.draft}m überschreitet Limit {zone.max_draft}m der Zone '{zone.name}'."
            )
        if pos < 0 or pos + width > instance.quay_length + 1e-9:
            violations.append(f"{ship.name}: Belegung {pos}-{pos + width}m überschreitet den Kai.")

    items = list(plan.items())
    for i in range(len(items)):
        idx_a, (start_a, pos_a) = items[i]
        ship_a = ships_by_index[idx_a]
        for j in range(i + 1, len(items)):
            idx_b, (start_b, pos_b) = items[j]
            ship_b = ships_by_index[idx_b]
            time_overlap = _intervals_overlap(
                start_a, start_a + ship_a.handling_time, start_b, start_b + ship_b.handling_time
            )
            if not time_overlap:
                continue
            width_a = instance.occupied_width(ship_a)
            width_b = instance.occupied_width(ship_b)
            space_overlap = _intervals_overlap(pos_a, pos_a + width_a, pos_b, pos_b + width_b)
            if space_overlap:
                violations.append(
                    f"{ship_a.name} (t={start_a}-{start_a + ship_a.handling_time}h, "
                    f"Pos {pos_a}-{pos_a + ship_a.length}m) und {ship_b.name} "
                    f"(t={start_b}-{start_b + ship_b.handling_time}h, Pos {pos_b}-{pos_b + ship_b.length}m) "
                    "überlappen räumlich-zeitlich (inkl. Sicherheitsabstand)."
                )
    return len(violations) == 0, violations


def evaluate(instance, plan, label=""):
    ships_by_index = {s.index: s for s in instance.ships}
    per_ship = {}
    by_priority = defaultdict(list)
    total_weighted_wait = 0.0
    total_wait = 0.0
    last_departure = 0

    for idx, (start, pos) in plan.items():
        ship = ships_by_index[idx]
        wait = start - ship.arrival
        per_ship[idx] = {"start": start, "pos": pos, "wait": wait}
        by_priority[ship.priority].append(wait)
        total_weighted_wait += ship.weight * wait
        total_wait += wait
        last_departure = max(last_departure, start + ship.handling_time)

    avg_wait_by_priority = {
        prio: (sum(waits) / len(waits) if waits else 0.0) for prio, waits in by_priority.items()
    }

    return {
        "label": label,
        "plan": per_ship,
        "total_weighted_wait": total_weighted_wait,
        "total_wait": total_wait,
        "avg_wait_by_priority": avg_wait_by_priority,
        "last_departure": last_departure,
        "n_ships": len(plan),
    }


def comparison_table(results):
    import pandas as pd

    rows = []
    for r in results:
        row = {
            "Methode": r["label"],
            "Gewichtete Wartezeit (Prioritäts-Score)": round(r["total_weighted_wait"], 1),
            "Wartezeit gesamt (h)": round(r["total_wait"], 1),
            "Letzte Abfahrt (h)": r["last_departure"],
        }
        for prio in ("Mainliner", "Feeder", "Tramp"):
            row[f"Ø Wartezeit {prio} (h)"] = round(r["avg_wait_by_priority"].get(prio, 0.0), 1)
        rows.append(row)
    return pd.DataFrame(rows)
