"""Preset-Abstimmung per Sweep: traegt die Aussage jedes Presets im MITTEL ueber viele Flotten und Ziehungen, nicht nur bei den gewaehlten Seeds?

Aufruf (im Projektordner): ./venv/Scripts/python.exe tools/tune_presets.py <modus> [preset]
  population   Grundgesamtheit je Preset: Mittel und Median der Gewinne, Anteil besser/gleich/schlechter, Abnahmekriterien des Plans (Abschnitt 7)
  fleets       je Preset alle Kandidaten-Flotten (Seeds 0..79): Mittel ueber 20 Verspaetungs-Ziehungen, Nebenbedingungen, Abstand zum Median
  pick         waehlt je Preset Flotten-Seed und Verspaetungs-Seed (typisch UND rauschstabil) und gibt die PRESETS-Zeilen aus
  scan         Suche nach Preset-Parametern, die das Kriterium tragen (nur 'Leichte Verspaetung' und 'Ruhiger Hafen')

Grundsaetze (aus der Stapelplanung): Seeds nicht nach dem schoensten Einzelfall waehlen, sondern nahe am Median mehrerer Merkmale und rauschstabil (die Aussage
muss bei mindestens 90 % anderer Verspaetungs-Ziehungen halten); Kriterien an der Grundgesamtheit messen. Wegen der schiefen Verteilung (Median << Mittel)
gehoeren Mittel UND Median in die Pruefung."""
import random
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, ".")
import rb_constants as C
from rb_delays import scenario_delays
from rb_evaluation import delay_sweep, distribution, run_strategies
from rb_presets import fleet_instance
from rb_scenario import is_playable
from rb_stories import criteria, draw_holds, rel_of

S, P, N, F = C.STRAT_STARR, C.STRAT_PUFFER, C.STRAT_NEU, C.STRAT_PROGNOSE
FLEET_SEEDS = range(80)
DELAY_SEEDS = range(20)


def fleet_of(p):
    return (p["n_ships"], p["quay_length"], p["arrival_spread"], p["handling_avg"], p["mainliner_pct"])


def population_stats(name, n_inst=60, n_draws=5, preset=None):
    p = preset or C.PRESETS[name]
    sw = delay_sweep(*fleet_of(p)[:4], p["mainliner_pct"] / 100, p["delay_kind"], p["delay_mean"], p["buffer"], p["forecast_pct"],
                     n_instances=n_inst, n_draws=n_draws, deltas=(p["delay_mean"],), with_exact=False)
    base = sw.mean(S, 0)
    rel = {k: 100 * (base - sw.mean(k, 0)) / base if base else 0.0 for k in (P, N, F)}
    dist = {k: distribution(sw, k, p["delay_mean"]) for k in (P, N, F)}
    return sw, rel, dist


def _population_job(name):
    sw, rel, dist = population_stats(name)
    return name, sw.mean(S, 0), rel, dist


def cmd_population():
    names = list(C.PRESETS)
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(_population_job, names))
    for name, base, rel, dist in results:
        p = C.PRESETS[name]
        print(f"\n### {name}  {p}")
        print(f"starr {base:.1f} h je Schiff | Gewinn gegen starr: Puffer {rel[P]:+.1f} %, Neuplanung {rel[N]:+.1f} %, +Prognose {rel[F]:+.1f} %")
        for k in (P, N, F):
            d = dist[k]
            print(f"  {C.STRATEGY_SHORT[k].replace('<br>', ' '):22s} besser/gleich/schlechter {d.better:.0%}/{d.equal:.0%}/{d.worse:.0%} | Median {d.median_gain:+.1f} Mittel {d.mean_gain:+.1f}"
                  f" | Top-10%-Anteil {d.top10_share if d.top10_share is None else round(d.top10_share, 2)}")
        for ok, text in criteria(name, rel):
            print(("  OK   " if ok else "  FAIL ") + text)
        if name == "Ausreißer":
            d = dist[N]
            print(("  OK   " if d.median_gain <= 0.5 * d.mean_gain else "  FAIL ") + f"Median-Gewinn deutlich unter dem Mittel: {d.median_gain:.1f} gegen {d.mean_gain:.1f}")


# ---------------------------------------------------------------------------------------------------
# Flotten: je Kandidat 20 Verspaetungs-Ziehungen
# ---------------------------------------------------------------------------------------------------
def fleet_draws(p, fleet_seed, delay_seeds=DELAY_SEEDS):
    """Gesamtkosten je Strategie fuer 20 Ziehungen einer Flotte: Liste von Dicts, oder None wenn die Flotte nicht passt."""
    inst = fleet_instance(*fleet_of(p), fleet_seed)
    if not is_playable(inst):
        return None
    out = []
    for ds in delay_seeds:
        d = scenario_delays(inst, p["delay_mean"], p["delay_kind"], ds)
        out.append({o.key: o.wait_total for o in run_strategies(inst, d, p["delay_mean"], p["buffer"], p["forecast_pct"])})
    return out


def bootstrap_stability(name, rows, n_boot=300):
    """Rauschstabilitaet der MITTELWERT-Aussage: Anteil der Neuziehungen (Bootstrap aus den 20 Ziehungen), bei denen alle Kriterien des Presets gelten.
    Einzelne Ziehungen halten die Geschichte bewusst NICHT immer (in jedem fuenften Szenario verliert die Neuplanung) - das ist der Kernbefund der Demo,
    also kann Stabilitaet nur an der Mittelwert-Aussage gemessed werden, nicht an jeder einzelnen Ziehung."""
    rng = random.Random(len(rows) * 7919)
    hits = 0
    for _ in range(n_boot):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        hits += all(ok for ok, _ in criteria(name, rel_of(sample)))
    return hits / n_boot


def fleet_report(name):
    p = C.PRESETS[name]
    cands = []
    for fs in FLEET_SEEDS:
        rows = fleet_draws(p, fs)
        if rows is None:
            continue
        rel = rel_of(rows)
        cands.append({"seed": fs, "rel": rel, "stable": bootstrap_stability(name, rows), "ok": all(o for o, _ in criteria(name, rel)),
                      "single": sum(draw_holds(name, r) for r in rows) / len(rows), "rows": rows})
    return name, cands


def _target(name):
    """Zielwerte fuer 'typisch': die Mittelwerte der Grundgesamtheit (60 Flotten x 5 Ziehungen), nicht der Median der Flotten-Mittel (der kann bei
    ruhigen Hafen 0 sein, weil in vielen Flotten gar nichts wartet)."""
    return population_stats(name)[1]


def _rank(name, cands, target):
    good = [c for c in cands if c["ok"] and c["stable"] >= 0.9]
    return sorted(good, key=lambda c: sum(abs(c["rel"][k] - target[k]) / (abs(target[k]) + 1) for k in (P, N, F)))


def _fmt(rel):
    return ", ".join(f"{C.STRATEGY_SHORT[k].split('<')[0]} {rel[k]:+.1f} %" for k in (P, N, F))


def _fleet_job(name):
    name, cands = fleet_report(name)
    return name, cands, _target(name)


def cmd_fleets(only=None):
    names = [only] if only else list(C.PRESETS)
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(_fleet_job, names))
    for name, cands, target in results:
        print(f"\n### {name}: {len(cands)} spielbare Flotten; Grundgesamtheit (Ziel): {_fmt(target)}")
        print(f"  Kriterien erfuellt (Flotten-Mittel): {sum(c['ok'] for c in cands)} von {len(cands)}; rauschstabil (Bootstrap) >= 90 %: {sum(c['stable'] >= 0.9 for c in cands)}")
        for c in _rank(name, cands, target)[:5]:
            print(f"  seed {c['seed']:3d} | {_fmt(c['rel'])} | stabil {c['stable']:.0%} | einzelne Ziehungen {c['single']:.0%}")


def cmd_pick():
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(_fleet_job, list(C.PRESETS)))
    print("Vorschlag (Flotten-Seed, Verspaetungs-Seed): typische Flotte nahe an der Grundgesamtheit, Ziehung nahe am Median der Gewinne der Flotte\n")
    for name, cands, target in results:
        ranked = _rank(name, cands, target)
        if not ranked:
            print(f"{name}: KEIN Kandidat erfuellt Kriterien und Stabilitaet")
            continue
        best = ranked[0]
        gains = [r[S] - r[N] for r in best["rows"]]
        med_gain = st.median(gains)
        ok_draws = [i for i, r in enumerate(best["rows"]) if draw_holds(name, r)]
        if not ok_draws:
            print(f"{name}: Flotte {best['seed']} hat keine Ziehung, in der die Geschichte haelt")
            continue
        dseed = min(ok_draws, key=lambda i: abs(gains[i] - med_gain))
        print(f"{name}: seed={best['seed']}, delay_seed={dseed}  (Flotte: {_fmt(best['rel'])}; stabil {best['stable']:.0%}, einzelne Ziehungen {best['single']:.0%}; "
              f"Ziehung: Gewinn {gains[dseed]:+.1f} h, Median der Flotte {med_gain:+.1f} h)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "population"
    if mode == "population":
        cmd_population()
    elif mode == "fleets":
        cmd_fleets(sys.argv[2] if len(sys.argv) > 2 else None)
    elif mode == "pick":
        cmd_pick()
    else:
        raise SystemExit(__doc__)
