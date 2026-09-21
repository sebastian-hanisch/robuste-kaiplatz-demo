"""Verspätungen: Fahrplan-Ankunft (ETA) a_i ist bekannt, die tatsächliche Ankunft ist a'_i = a_i + v_i mit ganzzahliger Verspätung v_i >= 0.

Zwei Arten mit demselben Mittelwert delta:
  exp   Exponentialverteilung mit Mittel delta (gleichmäßig)
  tail  Ausreißer: 80 % pünktlich, 20 % exponentialverteilt mit Mittel 5*delta
Eigener Zufallsstrom: Die Verspätungen hängen nur von (Seed, Mittel, Art, Schiffszahl) ab, nie vom Seed der Flotte."""

import dataclasses
import random

import rb_constants as C


def draw_delays(inst, mean, rng, kind="exp"):
    """Verspätung je Schiff in ganzen Stunden (>= 0), gezogen aus `rng` in Schiffs-Reihenfolge."""
    if kind not in C.DELAY_KINDS:
        raise ValueError(f"unbekannte Verspätungsart: {kind!r}")
    if mean < 0:
        raise ValueError("mittlere Verspätung darf nicht negativ sein")
    out = {}
    for s in inst.ships:
        if mean == 0:
            out[s.index] = 0
        elif kind == "exp":
            out[s.index] = round(rng.expovariate(1.0 / mean))
        elif rng.random() < C.TAIL_LATE_SHARE:
            out[s.index] = round(rng.expovariate(1.0 / (C.TAIL_SCALE * mean)))
        else:
            out[s.index] = 0
    return out


def scenario_delays(inst, mean, kind, seed):
    """Wie `draw_delays`, aber mit eigenem Strom aus `seed` (gleicher Seed = gleiche Ziehung)."""
    return draw_delays(inst, mean, random.Random(seed), kind)


def actual_arrivals(inst, delays):
    return {s.index: s.arrival + delays[s.index] for s in inst.ships}


def actual_instance(inst, delays):
    """Die Wirklichkeit: Ankünfte = tatsächliche Ankünfte; der Planungshorizont wächst mit (für den Exakt-Löser und die Prüfung nötig)."""
    ships = tuple(dataclasses.replace(s, arrival=s.arrival + delays[s.index]) for s in inst.ships)
    horizon = sum(s.handling_time for s in ships) + max((s.arrival for s in ships), default=0) + 24
    return dataclasses.replace(inst, ships=ships, horizon=max(inst.horizon, horizon))


def buffered_instance(inst, buffer_h):
    """Planungsinstanz für die Puffer-Strategie: jede Belegung um `buffer_h` Stunden verlängert (Lücken im Plan)."""
    if buffer_h < 0:
        raise ValueError("Puffer darf nicht negativ sein")
    ships = tuple(dataclasses.replace(s, handling_time=s.handling_time + buffer_h) for s in inst.ships)
    return dataclasses.replace(inst, ships=ships)
