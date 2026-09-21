"""Feste Hafenparameter und Referenz-Häfen der robusten Kaiplatzplanung.

Der Hafen ist bewusst fest (Zonen, Tiefgang, Sicherheitsabstand entsprechen "Volle Kaikapazität" der
berth-allocation-demo); veränderlich sind nur Flottengröße, Kailänge, Ankunftsfenster, Liegezeit und
Mainliner-Anteil. Regler-Grenzen und Demo-Presets kommen später (rb_presets.py)."""

# Fest: Tiefenzonen, Schiffsgrößen-Streuung, Sicherheitsabstand
DEEP_ZONE_FRACTION = 0.5
DEEP_DRAFT_LIMIT = 15.0
LENGTH_AVG = 180
LENGTH_VARIABILITY = 0.25
DRAFT_AVG = 10.0
DRAFT_VARIABILITY = 0.2
HANDLING_VARIABILITY = 0.3
SAFETY_MARGIN = 15

# Vorgabewerte der veränderlichen Größen (= "Volle Kaikapazität")
N_SHIPS_DEFAULT = 9
QUAY_LENGTH_DEFAULT = 600
ARRIVAL_SPREAD_DEFAULT = 30
HANDLING_AVG_DEFAULT = 14
MAINLINER_FRACTION_DEFAULT = 0.3
SEED_DEFAULT = 7

# Regler: Grenzen und Vorgaben. Die Kailänge beginnt bei 500 m: darunter passen die Schiffe des festen Hafens (Zonen von 250 m und weniger) oft
# nicht mehr an den Kai (gemessen: bei 10 Schiffen nur 33 % der Flotten spielbar bei 500 m, 65 % bei 550 m, 85 % bei 600 m).
N_SHIPS_RANGE = (4, 10)               # bis 10: der Exakt-Löser bleibt schnell (ab 12 Schiffen oft ans Zeitlimit)
QUAY_LENGTH_RANGE = (500, 900)
ARRIVAL_SPREAD_RANGE = (12, 72)
HANDLING_AVG_RANGE = (8, 24)
MAINLINER_PCT_RANGE, MAINLINER_PCT_DEFAULT = (0, 60), 30      # ganze Prozent, Umrechnung erst beim Verbrauchen
SEED_RANGE = (0, 9999)
DELAY_MEAN_RANGE, DELAY_MEAN_DEFAULT = (0, 16), 8
DELAY_KIND_DEFAULT = "exp"
DELAY_SEED_DEFAULT = 3
BUFFER_RANGE, BUFFER_DEFAULT = (0, 8), 1
FORECAST_PCT_RANGE, FORECAST_PCT_STEP, FORECAST_PCT_DEFAULT = (0, 200), 10, 100
DELAY_KIND_LABELS = {"exp": "gleichmäßig", "tail": "Ausreißer"}

# Neuplanung: Suchzüge der Tausch-Suche je Neuplanung (in der Messreihe bei 40 gegen 300 gesättigt, weniger ist klar schlechter)
REPLAN_MAX_MOVES = 40
# Suchzüge des Startplans (Plan auf den Fahrplan-Ankünften)
STATIC_PLAN_MAX_MOVES = 300

# Hellsehen (CP-SAT mit den tatsächlichen Ankünften): Zeitlimit in Sekunden; danach gilt das Ergebnis als "nicht bewiesen"
EXACT_TIME_LIMIT_SECONDS = 10

# Strategien (Schlüssel -> Beschriftung, in Anzeigereihenfolge); "starr" ist die Referenz aller Vergleiche
STRAT_STARR, STRAT_PUFFER, STRAT_NEU, STRAT_PROGNOSE, STRAT_EXACT = "starr", "puffer", "neuplanung", "prognose", "hellsehen"
STRATEGY_LABELS = {
    STRAT_STARR: "⏱️ Starrer Plan",
    STRAT_PUFFER: "🧱 Puffer",
    STRAT_NEU: "🔄 Neuplanung",
    STRAT_PROGNOSE: "🔮 Neuplanung + Prognose",
    STRAT_EXACT: "🧮 Hellsehen (Exakt)",
}
STRATEGY_KEYS = tuple(STRATEGY_LABELS)
# Kurznamen für Achsenbeschriftungen (ohne Emoji, mit Zeilenumbruch, damit nebeneinanderstehende Balken nicht überlappen)
STRATEGY_SHORT = {
    STRAT_STARR: "Starr", STRAT_PUFFER: "Puffer", STRAT_NEU: "Neuplanung", STRAT_PROGNOSE: "Neuplanung<br>+ Prognose", STRAT_EXACT: "Hellsehen",
}
BASELINE = STRAT_STARR

# Kostenkurve: Verspätungsraster, Instanzen (Seeds 0.., unabhängig vom eingestellten Seed) x Ziehungen je Instanz;
# das eingestellte delta kommt zum Raster hinzu, damit die Kennzahlen dafür exakt und nicht interpoliert sind
SWEEP_DELTAS = (0, 4, 8, 12, 16)
SWEEP_INSTANCES = 15
SWEEP_DRAWS = 2
SWEEP_EXACT_TIME_LIMIT_SECONDS = 1
# Fokus-Stichprobe beim eingestellten delay (ohne Hellsehen, dafür mehr Szenarien): Verteilung, Urteil und Gewinne brauchen mehr Szenarien
# als die Kurve, damit ein echter Unterschied nicht im Rauschen untergeht (30 Szenarien reichten oft nicht für "klar")
FOCUS_INSTANCES = 30
FOCUS_DRAWS = 3
# Urteil: "klar" heißt gepaarte Differenz > VERDICT_Z Standardfehler
VERDICT_Z = 2.0
# Verteilung: Unterschiede bis zu dieser Größe (gewichtete Wartestunden je Szenario) zählen als "gleich"
TIE_TOLERANCE = 0.5

STRATEGY_COLORS = {
    STRAT_STARR: "#8a94a3", STRAT_PUFFER: "#2a6fb0", STRAT_NEU: "#c77700", STRAT_PROGNOSE: "#2e7d4f", STRAT_EXACT: "#7a3fb0",
}
STRATEGY_DASH = {STRAT_EXACT: "dash"}           # Hellsehen ist keine Strategie, sondern die untere Schranke: gestrichelt
STRATEGY_DESCRIPTIONS = {
    STRAT_STARR: "**Starrer Plan.** Der Plan wird auf den Fahrplan-Ankünften gemacht und dann so gut es geht ausgeführt: Positionen und Reihenfolge am Kai bleiben, "
                 "ein verspätetes Schiff schiebt alle nach, die räumlich hinter ihm liegen (Rechts-Verschiebung). Kein Anlegen vor dem geplanten Fenster.",
    STRAT_PUFFER: "**Puffer.** Der Plan rechnet mit einer um den eingestellten Puffer verlängerten Liegezeit und lässt so Lücken für Verspätungen. Die Lücken kosten "
                  "Wartezeit, auch wenn alle pünktlich sind.",
    STRAT_NEU: "**Neuplanung.** Bei jeder Ankunft und wenn ein geplantes Fenster ohne Schiff verstreicht, werden alle noch nicht liegenden Schiffe neu eingeplant. "
               "Liegende Schiffe sind feste Hindernisse; noch nicht angekommene Schiffe zählen ab ihrer Fahrplan-Ankunft, frühestens ab der nächsten Stunde.",
    STRAT_PROGNOSE: "**Neuplanung + Prognose.** Wie die Neuplanung, aber noch nicht angekommene Schiffe werden erst nach der erwarteten Restverspätung eingeplant "
                    "(einstellbar als Anteil der mittleren Verspätung). Zeigt, was eine gute Vorhersage wert ist und was eine falsche kostet.",
    STRAT_EXACT: "**Hellsehen.** Der beste Plan, den man mit Kenntnis aller tatsächlichen Ankünfte im Voraus wählen würde (CP-SAT). Nicht erreichbar, nur ein Maßstab: "
                 "Der Abstand einer Strategie dazu ist der Preis der Unsicherheit.",
}
PRIORITY_COLORS = {"Mainliner": "#d62728", "Feeder": "#1f77b4", "Tramp": "#7f7f7f"}
PRIORITIES = ("Mainliner", "Feeder", "Tramp")
ZONE_COLORS = {"Tiefwasser": "rgba(31,119,180,0.08)", "Flachwasser": "rgba(255,127,14,0.10)"}
ETA_COLOR = "#e8850c"                # Fahrplan-Ankunft und Verspätungsstrecke
MARKER_LINE_COLOR = "#808895"        # mittleres Grau: auf hellem und dunklem Grund sichtbar
OUTCOME_COLORS = {"better": "#2e7d4f", "equal": "#b8bfc9", "worse": "#c0392b"}
CHART_HEIGHT = 420

DELAY_KINDS = ("exp", "tail")
# "tail": Anteil pünktlicher Schiffe ist 1 - TAIL_LATE_SHARE, die übrigen sind exponentialverteilt mit dem TAIL_SCALE-fachen Mittel
TAIL_LATE_SHARE = 0.2
TAIL_SCALE = 5

# Referenz-Häfen der Vorab-Messreihe (hafen-planung/messreihe_kai); nur für die Tests, die deren Werte reproduzieren
REFERENCE_PRESETS = {
    "Ruhiger Feederhafen": dict(
        n_ships=5, quay_length=500, deep_zone_fraction=0.4, deep_draft_limit=13.0,
        length_avg=140, length_variability=0.2, draft_avg=8.0, draft_variability=0.15,
        handling_avg=10, handling_variability=0.25, arrival_spread=48, mainliner_fraction=0.1,
        safety_margin=12, seed=3,
    ),
    "Mainliner-Stoßzeit trifft Tiefwasser-Engpass": dict(
        n_ships=7, quay_length=700, deep_zone_fraction=0.4, deep_draft_limit=16.0,
        length_avg=200, length_variability=0.15, draft_avg=12.0, draft_variability=0.15,
        handling_avg=16, handling_variability=0.3, arrival_spread=24, mainliner_fraction=0.5,
        safety_margin=15, seed=1,
    ),
    "Volle Kaikapazität": dict(
        n_ships=9, quay_length=600, deep_zone_fraction=0.5, deep_draft_limit=15.0,
        length_avg=180, length_variability=0.25, draft_avg=10.0, draft_variability=0.2,
        handling_avg=14, handling_variability=0.3, arrival_spread=30, mainliner_fraction=0.3,
        safety_margin=15, seed=7,
    ),
}

# Beispielszenarien (Feldnamen wie in rb_presets.PRESET_STATE_KEYS); per Sweep abgestimmt (tools/tune_presets.py, Kriterien in rb_stories.py,
# Ergebnis in tools/PRESET_SWEEP.md). Seeds nicht nach dem schönsten Einzelfall gewählt, sondern typisch (nahe an der Grundgesamtheit) und rauschstabil.
_BASE = dict(n_ships=9, quay_length=600, arrival_spread=30, handling_avg=14, mainliner_pct=30, seed=7, delay_mean=8, delay_kind="exp",
             delay_seed=3, buffer=1, forecast_pct=100)
PRESETS = {
    "Pünktlich": dict(_BASE, seed=14, delay_mean=0),
    "Leichte Verspätung": dict(_BASE, seed=56, delay_seed=6, delay_mean=4),
    "Große Verspätung": dict(_BASE, seed=14, delay_seed=14, delay_mean=12),
    "Ausreißer": dict(_BASE, seed=6, delay_seed=13, delay_mean=8, delay_kind="tail"),
    "Ruhiger Hafen": dict(_BASE, n_ships=5, quay_length=700, arrival_spread=72, handling_avg=10, mainliner_pct=10, seed=42, delay_seed=3, delay_mean=12, buffer=4),
}
