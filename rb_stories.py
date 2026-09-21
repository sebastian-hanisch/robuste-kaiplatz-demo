"""Abnahmekriterien der Presets (Plan, Abschnitt 7): Welche Geschichte erzählt jedes Beispielszenario, und woran erkennt man, dass sie trägt?

Einzige Quelle für `tools/tune_presets.py` (Abstimmung) und `tests/test_preset_stories.py` (Abnahme). Gain-Angaben `rel` sind Prozent der Kosten des
starren Plans (Mittel je Schiff), positiv = die Strategie ist besser als starr."""

import rb_constants as C

S, P, N, F = C.STRAT_STARR, C.STRAT_PUFFER, C.STRAT_NEU, C.STRAT_PROGNOSE


def criteria(name, rel):
    """Mittelwert-Kriterien. rel: {Strategie: Gewinn gegen starr in %}. Rückgabe: Liste (erfüllt, Text)."""
    puf, neu, prog = rel[P], rel[N], rel[F]
    if name == "Pünktlich":
        return [(puf <= -5, f"Puffer >= 5 % teurer als starr: {puf:+.1f} %"), (abs(neu) <= 3, f"Neuplanung innerhalb +-3 % von starr: {neu:+.1f} %")]
    if name == "Leichte Verspätung":
        return [(puf <= 0.5, f"Puffer nicht besser als starr: {puf:+.1f} %"), (neu <= 10, f"Neuplanung hoechstens 10 % besser: {neu:+.1f} %")]
    if name == "Große Verspätung":
        return [(neu >= 15, f"Neuplanung >= 15 % besser: {neu:+.1f} %"), (prog >= 30, f"mit Prognose >= 30 % besser: {prog:+.1f} %")]
    if name == "Ausreißer":
        return [(neu >= 25, f"Neuplanung >= 25 % besser: {neu:+.1f} %")]
    if name == "Ruhiger Hafen":
        return [(puf > 0, f"Puffer besser als starr: {puf:+.1f} %"), (neu > puf, f"Neuplanung besser als Puffer: {neu:+.1f} % gegen {puf:+.1f} %")]
    raise KeyError(name)


def draw_holds(name, cost):
    """Gilt die Geschichte in EINER Ziehung? cost: {Strategie: gewichtete Gesamtwartezeit}. Einzelne Ziehungen halten sie bewusst nicht immer
    (in jedem fünften Szenario verliert die Neuplanung); geprüft wird sie deshalb am gewählten Seed und im Mittel, nicht in jeder Ziehung."""
    if name == "Pünktlich":
        return cost[P] > cost[S] and abs(cost[N] - cost[S]) <= 0.03 * max(cost[S], 1)
    if name == "Leichte Verspätung":
        return cost[N] <= cost[S] * 1.05
    if name == "Große Verspätung":
        return cost[N] <= cost[S] and cost[F] < cost[N]
    if name == "Ausreißer":
        return cost[N] < cost[S] and cost[F] <= cost[N]
    if name == "Ruhiger Hafen":
        return cost[P] < cost[S] and cost[N] <= cost[P]
    raise KeyError(name)


def rel_of(rows):
    """Gewinn gegen starr in % aus einer Liste von Kosten-Dicts (Mittel über die Zeilen)."""
    import statistics
    base = statistics.fmean(r[S] for r in rows)
    return {k: 100 * (base - statistics.fmean(r[k] for r in rows)) / base if base else 0.0 for k in (P, N, F)}
