"""Gemeinsame Testhilfen."""

from berth_scenario import Instance, Ship, Zone


def ship(index, length, arrival, handling, priority="Tramp", weight=1.0, draft=5.0):
    return Ship(index=index, name=f"Schiff {index + 1}", length=length, draft=draft, arrival=arrival,
                handling_time=handling, priority=priority, weight=weight)


def manual_instance(ships, quay_length=100, safety_margin=0):
    """Handgebaute Instanz mit einer einzigen Tiefenzone (alle Schiffe passen tiefgangmäßig überall)."""
    zones = (Zone(name="Tiefwasser", start=0, end=quay_length, max_draft=15.0),)
    horizon = sum(s.handling_time for s in ships) + max((s.arrival for s in ships), default=0) + 24
    return Instance(quay_length=quay_length, zones=zones, ships=tuple(ships), safety_margin=safety_margin, horizon=horizon)
