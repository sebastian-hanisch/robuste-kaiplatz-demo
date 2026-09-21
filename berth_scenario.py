"""Instanzerzeugung: Schiffe (Länge, Tiefgang, Ankunft, Priorität) entlang eines Kais mit
tiefenabhängigen Zonen.

Bewusste Design-Entscheidung, aus quaycrane-demo gelernt: dort führte die Umrechnung
stetiger Minutenwerte in skalierte CP-SAT-Ganzzahlen (SCALE, `round()` vs. `math.ceil()`) zu
mehreren, mühsam gefundenen Rundungsfehlern (siehe [[project_quaycrane_demo_venv]], Fund 6).
Hier arbeiten Heuristik, Prüfung UND CP-SAT-Modell durchgehend mit ECHTEN Ganzzahlen (Meter,
Stunden) - keine Skalierung, also auch keine Rundungsdifferenz zwischen den drei Wegen."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Zone:
    name: str
    start: int  # Kai-Position, Meter
    end: int
    max_draft: float  # Meter


@dataclass(frozen=True)
class Ship:
    index: int
    name: str
    length: int  # Meter
    draft: float  # Meter
    arrival: int  # frühestmögliche Anlegezeit, Stunden
    handling_time: int  # Stunden, fix
    priority: str  # "Mainliner" | "Feeder" | "Tramp"
    weight: float  # Zielfunktionsgewicht (Wartezeit-Priorität)


PRIORITY_WEIGHTS = {"Mainliner": 3.0, "Feeder": 1.5, "Tramp": 1.0}
SHALLOW_DRAFT_RATIO = 0.6  # Flachwasserzone erlaubt nur diesen Anteil des Tiefwasser-Tiefgangs


@dataclass(frozen=True)
class Instance:
    quay_length: int
    zones: tuple  # Zone, aufsteigend, lückenlos [0, quay_length]
    ships: tuple  # Ship
    safety_margin: int  # Meter Pufferabstand, den JEDES Schiff hinter sich freihält
    horizon: int  # Stunden, sichere obere Schranke für die Planung

    def occupied_width(self, ship):
        """Der tatsächlich für Nichtüberlappung reservierte Kai-Abschnitt: Schiffslänge PLUS
        Sicherheitsabstand. Indem jedes Schiff diesen Puffer als Teil seiner eigenen Breite
        mitbringt, erzwingt reine Rechteck-Nichtüberlappung (siehe berth_cp_solver.py,
        `AddNoOverlap2D`) automatisch den vollen Abstand zwischen je zwei Nachbarn, ohne eigene
        Abstands-Constraints."""
        return ship.length + self.safety_margin

    def compatible_zones(self, ship):
        return [z for z in self.zones if z.max_draft >= ship.draft]

    def feasible_start_ranges(self, ship):
        """Liste von (lo, hi) Kai-Positionen (Meter) - mögliche Startpositionen für `ship`,
        eingeschränkt auf tiefgang-kompatible Zonen, die für sich allein breit genug für
        `occupied_width(ship)` sind. Ein Schiff liegt immer vollständig in EINER Zone - es darf
        nicht über eine zu flache Zonengrenze hinausragen."""
        width = self.occupied_width(ship)
        ranges = []
        for z in self.compatible_zones(ship):
            if (z.end - z.start) >= width:
                ranges.append((z.start, z.end - width))
        return ranges

    def is_trivially_infeasible(self):
        """True, wenn schon ein EINZELNES Schiff für sich allein (unabhängig von allen anderen)
        nirgends am Kai Platz hätte - zu tiefgängig für jede Zone, oder länger (inkl.
        Sicherheitsabstand) als jede tiefgang-kompatible Zone breit ist. Analog zu
        `quaycrane_scenario.Instance.is_trivially_infeasible` - muss vor jedem
        Konstruktionsversuch geprüft werden."""
        return any(not self.feasible_start_ranges(s) for s in self.ships)


def generate_instance(
    n_ships,
    quay_length,
    deep_zone_fraction,
    deep_draft_limit,
    length_avg,
    length_variability,
    draft_avg,
    draft_variability,
    handling_avg,
    handling_variability,
    arrival_spread,
    mainliner_fraction,
    safety_margin,
    seed,
):
    rng = random.Random(seed)
    deep_end = round(quay_length * deep_zone_fraction)
    zones = (
        Zone(name="Tiefwasser", start=0, end=deep_end, max_draft=deep_draft_limit),
        Zone(name="Flachwasser", start=deep_end, end=quay_length, max_draft=round(deep_draft_limit * SHALLOW_DRAFT_RATIO, 1)),
    )

    def bounded_gauss(avg, variability, lo):
        spread = max(0.0, avg * variability)
        return max(lo, rng.gauss(avg, spread)) if spread > 0 else float(avg)

    ships = []
    for i in range(n_ships):
        length = max(20, round(bounded_gauss(length_avg, length_variability, 20)))
        draft = round(bounded_gauss(draft_avg, draft_variability, 3.0), 1)
        handling = max(2, round(bounded_gauss(handling_avg, handling_variability, 2)))
        arrival = rng.randint(0, max(0, arrival_spread))
        priority = "Mainliner" if rng.random() < mainliner_fraction else rng.choice(["Feeder", "Tramp"])
        ships.append(
            Ship(
                index=i,
                name=f"Schiff {i + 1}",
                length=length,
                draft=draft,
                arrival=arrival,
                handling_time=handling,
                priority=priority,
                weight=PRIORITY_WEIGHTS[priority],
            )
        )

    total_handling = sum(s.handling_time for s in ships)
    horizon = total_handling + max((s.arrival for s in ships), default=0) + 24

    return Instance(
        quay_length=quay_length, zones=zones, ships=tuple(ships), safety_margin=safety_margin, horizon=horizon
    )
