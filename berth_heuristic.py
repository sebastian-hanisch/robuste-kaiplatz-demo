"""Zwei Konstruktionen plus lokale Suche, alle auf derselben `order`-Repräsentation (Liste von
Schiffsindizes in Einfüge-Reihenfolge):

- fcfs_construction: Ankunftsreihenfolge (First-Come-First-Served) - naiver Vergleichspunkt.
- priority_construction: erst nach Prioritätsgewicht, dann Ankunft - Mainliner dürfen sich die
  besten Slots zuerst sichern.
- greedy_and_polish: die bessere der beiden Startreihenfolgen, anschließend lokale Suche
  (paarweiser Tausch der Einfüge-Reihenfolge).

Konstruktionsprinzip: jedes Schiff wird einzeln eingefügt, an der frühesten Position, die bei
einem der Kandidaten-Zeitpunkte frei ist (siehe `_insert`). Anders als bei quaycrane-demo (wo
dieselbe Grundidee wegen Kran-Interferenz-während-Fahrt viele Iterationen brauchte, siehe
[[project_quaycrane_demo_venv]]) ist der letzte Kandidat - der Zeitpunkt, zu dem JEDES bereits
eingeplante Schiff schon wieder abgelegt hat - hier PER KONSTRUKTION immer frei: an diesem
Zeitpunkt ist kein anderes Schiff mehr aktiv, und `Instance.is_trivially_infeasible` stellt vorab
sicher, dass jedes Schiff für sich allein irgendwo am Kai passt. Die Einfügung kann also nie
scheitern - kein Sonderfall, keine Ausnahme nötig."""

import random

from berth_evaluation import evaluate


def _earliest_free_position(lo, hi, width, occupied):
    """occupied: Liste von (p0, p1)-Intervallen, die einander garantiert nicht überlappen (sie
    stammen aus einem bereits zulässigen Teil-Plan). Kleinste Startposition in [lo, hi], für die
    [start, start+width) mit keinem davon überlappt, oder None."""
    start = lo
    for p0, p1 in sorted(occupied):
        if start + width <= p0:
            break
        start = max(start, p1)
    return start if start <= hi else None


def _insert(instance, plan, ship):
    """Fügt `ship` in den bestehenden (zulässigen) `plan` (dict ship_index -> (start, pos)) ein
    und gibt (start, pos) zurück. Kandidaten-Startzeiten: die Ankunft selbst, plus jeder
    Zeitpunkt, zu dem ein bereits eingeplantes Schiff wieder abgelegt hat (nur DORT kann neuer
    Platz frei werden - ein späterer "Start" eines anderen Schiffs macht die Lage nur enger,
    nie freier). Für jede Kandidatenzeit wird über alle tiefgang-kompatiblen Zonen die früheste
    freie Position gesucht; die erste erfolgreiche Kombination (kleinste Zeit, dann kleinste
    Position) wird genommen."""
    width = instance.occupied_width(ship)
    zone_ranges = [
        (z, z.start, z.end - width) for z in instance.compatible_zones(ship) if (z.end - z.start) >= width
    ]

    departures = {start + instance.ships[idx].handling_time for idx, (start, _pos) in plan.items()}
    candidates = sorted(t for t in ({ship.arrival} | departures) if t >= ship.arrival)

    for t in candidates:
        occupied_by_zone = {z.name: [] for z, _lo, _hi in zone_ranges}
        for idx, (other_start, other_pos) in plan.items():
            other = instance.ships[idx]
            if not (other_start < t + ship.handling_time and t < other_start + other.handling_time):
                continue
            zone = next((z for z, _lo, _hi in zone_ranges if z.start <= other_pos < z.end), None)
            if zone is None:
                continue  # `other` liegt in einer Zone, die für `ship` ohnehin nicht in Frage kommt
            occupied_by_zone[zone.name].append((other_pos, other_pos + instance.occupied_width(other)))

        best_pos = None
        for zone, lo, hi in zone_ranges:
            pos = _earliest_free_position(lo, hi, width, occupied_by_zone[zone.name])
            if pos is not None and (best_pos is None or pos < best_pos):
                best_pos = pos
        if best_pos is not None:
            return t, best_pos

    # Unerreichbar, solange `Instance.is_trivially_infeasible` vorab geprüft wurde (siehe
    # Docstring oben) - hier nur als klarer Fehler statt eines stillen falschen Ergebnisses.
    raise RuntimeError(f"Keine zulässige Einfügung für {ship.name} gefunden - Szenario prüfen.")


def _build(instance, order):
    plan = {}
    for idx in order:
        ship = instance.ships[idx]
        plan[idx] = _insert(instance, plan, ship)
    return plan


def fcfs_construction(instance):
    """Ankunftsreihenfolge - wer zuerst da ist, wird zuerst (und damit meist am besten)
    eingeplant, unabhängig von Prioritätsgewicht. Naiver Vergleichspunkt."""
    order = sorted(range(len(instance.ships)), key=lambda i: (instance.ships[i].arrival, i))
    return _build(instance, order)


def priority_construction(instance):
    """Erst nach Prioritätsgewicht (Mainliner zuerst), dann nach Ankunft - höher priorisierte
    Schiffe sichern sich die besten verfügbaren Slots zuerst; niedriger priorisierte weichen
    entsprechend stärker aus."""
    order = sorted(range(len(instance.ships)), key=lambda i: (-instance.ships[i].weight, instance.ships[i].arrival, i))
    return _build(instance, order)


def _weighted_wait_of(instance, order):
    plan = _build(instance, order)
    return evaluate(instance, plan)["total_weighted_wait"]


def local_search(instance, order, rng=None, max_moves=300):
    """Hill-Climbing auf der Einfüge-Reihenfolge: paarweiser Tausch zweier Schiffe in der
    Reihenfolge, neu gebaut und bewertet, akzeptiert nur echte Verbesserungen der gewichteten
    Wartezeit. Nie schlechter als der Startpunkt."""
    rng = rng or random.Random(0)
    best_order = list(order)
    best_score = _weighted_wait_of(instance, best_order)
    moves_used = 0
    improved = True

    while improved and moves_used < max_moves:
        improved = False
        n = len(best_order)
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        rng.shuffle(pairs)
        for i, j in pairs:
            if moves_used >= max_moves:
                break
            moves_used += 1
            candidate = list(best_order)
            candidate[i], candidate[j] = candidate[j], candidate[i]
            score = _weighted_wait_of(instance, candidate)
            if score < best_score - 1e-9:
                best_order, best_score, improved = candidate, score, True

    return best_order


def greedy_and_polish(instance, seed=0, max_moves=300):
    rng = random.Random(seed)
    candidates = [
        sorted(range(len(instance.ships)), key=lambda i: (instance.ships[i].arrival, i)),
        sorted(range(len(instance.ships)), key=lambda i: (-instance.ships[i].weight, instance.ships[i].arrival, i)),
    ]
    start_order = min(candidates, key=lambda o: _weighted_wait_of(instance, o))
    polished_order = local_search(instance, start_order, rng, max_moves=max_moves)
    return _build(instance, polished_order)
