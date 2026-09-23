# Robuste Kaiplatzplanung: Puffer oder Information? – Streamlit-Demo

**[→ Demo live ausprobieren](https://sebastianhanisch-robuste-kaiplatz-demo.streamlit.app/)**

Interaktive Fall-Demo zur **Kaiplatzplanung bei unpünktlichen Schiffen**: Die Kaiplatz-Zuteilung (`berth-allocation-demo`) geht davon aus, dass alle Schiffe
zur Fahrplan-Ankunft da sind. Hier kommen sie später, und die Wartezeit zählt ab der **tatsächlichen** Ankunft. Die Demo stellt zwei Antworten gegeneinander:
**Reserve im Plan** (Puffer) oder **Wissen im Betrieb** (Neuplanung, mit einer Prognose der Restverspätung sogar besser), und beantwortet die Frage:
**Was ist was wert, und wie sehr täuscht ein Mittelwert, wenn man nur einen Einzelfall sieht?**

Teil des Portfolios für die Website „Sebastian Hanisch – Operations Research und Machine Learning", Welle 1 der Hafen-Linie (neben `berth-allocation-demo`,
`quaycrane-demo`, `stapelplanung-demo` und `yard-demo`). Instanzen, Einfüge-Heuristik und Exakt-Löser stammen wortgleich aus der Kaiplatz-Zuteilung.

## Warum dieses Problem

Ein Kaiplan ist immer ein Plan auf Fahrplan-Ankünften, und die Wirklichkeit weicht ab. Zwei klassische Antworten: **Lücken lassen** (Puffer) oder **neu planen**, sobald
man mehr weiß. Der Puffer hat einen sicheren Preis (Wartezeit auch bei pünktlichen Schiffen), einen unsicheren Nutzen; die Neuplanung hat keinen Lückenpreis, nutzt aber nur, was
schon bekannt ist. Die Demo misst beides auf denselben Verspätungen und zeigt die **Verteilung** der Gewinne, denn sie sind schief: Der Mittelwert wird von wenigen Szenarien getragen,
und in jedem fünften verliert die Neuplanung sogar gegen den starren Plan.

## Modell

Ein Kai mit zwei Tiefenzonen (fest: Tiefwasser und Flachwasser, Sicherheitsabstand 15 m), Schiffe mit Länge, Tiefgang, Fahrplan-Ankunft (ETA), Liegezeit und Klassengewicht
(Mainliner 3, Feeder 1,5, Tramp 1). Die **tatsächliche Ankunft** ist ETA plus Verspätung (ganze Stunden, nie negativ, keine Verfrühung):

- **gleichmäßig**: exponentialverteilt mit dem eingestellten Mittel δ,
- **Ausreißer**: 80 % pünktlich, 20 % exponentialverteilt mit Mittel 5δ (**gleicher Mittelwert**, schwerer Rand).

Zielgröße: Σ Gewicht · (Anlegebeginn − tatsächliche Ankunft), im Bericht je Schiff. Formal im Expander „📐 Mathematische Formulierung".

## Methodik – vier Strategien und ein Referenzlöser

Alle Strategien sehen in jedem Szenario **dieselben Verspätungen** (gepaart).

- **Starrer Plan** (Referenz): Plan auf den ETAs, dann **Rechts-Verschiebung**: Positionen und räumliche Reihenfolge bleiben, Anlegebeginn = max(tatsächliche Ankunft,
  geplantes Fenster, Ende aller räumlich überlappenden Vorgänger).
- **Puffer**: Plan mit um b Stunden verlängerter Belegung (Lücken), Ausführung mit den echten Liegezeiten. Bei b = 0 identisch mit starr (Test).
- **Neuplanung**: bei jeder Ankunft und wenn ein geplantes Fenster ohne Schiff verstreicht werden alle noch nicht liegenden Schiffe neu eingeplant (Einfüge-Heuristik mit
  Tausch-Suche, 40 Suchzüge); liegende Schiffe sind feste Hindernisse; noch nicht angekommene zählen ab max(ETA, jetzt + r) mit r = 1.
- **Neuplanung + Prognose**: wie die Neuplanung, aber mit r = erwartete Restverspätung (Regler: Anteil der mittleren Verspätung).
- **Hellsehen** (Tab „Exakt"): CP-SAT mit allen tatsächlichen Ankünften im Voraus. **Untere Schranke**, nicht erreichbar; der Abstand einer Strategie dazu ist der
  **Preis der Unsicherheit**. Zeitlimit 10 s; ein Ergebnis ohne Beweis wird als „nicht bewiesen" gekennzeichnet, nie als Optimum ausgegeben.

Die Hauptansicht zeigt bewusst **keine „beste Strategie" pro Ziehung** (mit Rückblick gewählt wäre das irreführend, denn die Neuplanung verliert in etwa jedem fünften Szenario),
sondern vier Kennzahlen gegen den starren Plan und die ausdrückliche Meldung, dass dies **eine** Ziehung ist, mit den Anteilen besser/gleich/schlechter aus dem Kernabschnitt.

## Befunde (gemessen, keine Behauptungen)

Alle Zahlen stammen aus Simulationen mit diesem Code (Vorab-Messreihe in `hafen-planung/messreihe_kai/ERGEBNIS.md`, Presets in `tools/PRESET_SWEEP.md`).

| Frage | Befund |
|---|---|
| **Kostet ein Puffer?** | Immer. Bei pünktlichen Schiffen ist der Puffer von 1 h im vollen Hafen im Mittel etwa 11 bis 13 % teurer als starr und in 98 % der Szenarien schlechter. |
| **Puffer oder Neuplanung?** | Die Neuplanung schlägt den besten Puffer in allen 30 getesteten Zellen (3 Häfen × 2 Verspätungsarten × 5 Verspätungen). Ein Puffer lohnt sich nur in einem ruhigen Hafen mit großer Verspätung. |
| **Wert der Neuplanung** | Voller Hafen, gleichmäßig: etwa +6 % bei 4 h Verspätung, +21 % bei 12 h; mit Ausreißern (8 h) etwa +29 %. |
| **Wert der Prognose** | Zusätzlich etwa +16 bis +23 Prozentpunkte (12 h: +37 % statt +21 %; Ausreißer: +52 % statt +29 %). Selbst eine doppelt zu pessimistische Prognose ist im Mittel besser als keine. |
| **Mittelwerte täuschen** | Große Verspätung, Neuplanung: besser / gleich / schlechter = 65 / 16 / 19 % der Szenarien; Median-Gewinn 30 gegen Mittel 63 gewichtete Wartestunden je Szenario. Mit Ausreißern: Median 8 gegen Mittel 113, die besten 10 % der Szenarien liefern etwa die Hälfte des Gewinns. |
| **Preis der Unsicherheit** | Bis etwa +16 (gleichmäßig) bzw. +42 (Ausreißer, Stoßzeit) Wartestunden je Schiff. Die Kosten des **Hellsehens sinken mit der Verspätung**: Gezählt wird nur die Wartezeit im Hafen, und verspätete Ankünfte entzerren den Kai. |
| **Plan-Unruhe** | Kaipositionen ändern sich kaum (meist eines von neun Schiffen), aber die Neuplanung plant je Szenario 6- bis 40-mal neu, und die angekündigten Anlegezeiten wandern. Wird gezählt, nicht bepreist. |
| **Exakte Neuplanung** | CP-SAT statt Heuristik bei jeder Neuplanung (in allen 2018 Fällen bewiesen optimal): nur etwa 1 bis 7 % besser bei 15-fachem Rechenaufwand. Die Heuristik ist gut genug. |
| **Reichweite des Exakt-Lösers** | Bis 10 Schiffe im Median unter 0,1 s (max. 0,44 s); 12 Schiffe Median 1,7 s (2 von 18 nicht bewiesen); 15 Schiffe 16 von 18 nicht bewiesen. Der Schiffsregler endet deshalb bei 10. |

## Ehrliche Grenzen

- **Nur Verspätungen, keine Verfrühung**; **feste Liegezeit** (kein Kranzahl-Effekt, das gehört zur `quaycrane-demo`); **ein Kai**.
- **Die Neuplanung ist kostenlos und sofort umsetzbar.** Lotsen, Schlepper, Mannschaften und Vorlaufzeiten sind nicht modelliert; die Unruhe im Plan wird gezählt, nicht bepreist.
- **Die starre Ausführung ist bewusst einfach** (Rechts-Verschiebung); eine klügere starre Ausführung nähert sich der Neuplanung.
- **Die Verspätungsverteilungen sind Annahmen**, keine Echtdaten. Zwei Arten mit gleichem Mittelwert zeigen, wie sehr der Rand zählt.
- **Der Hafen ist fest** (Zonen, Tiefgänge, Sicherheitsabstand). Unter etwa 550 m Kailänge passen die längsten Schiffe oft nicht in eine Zone: Bei 500 m sind nur etwa ein Drittel der zufälligen
  10-Schiffe-Flotten spielbar. Die Demo meldet das und sucht auf Knopfdruck eine passende Flotte.
- **Zielgröße nur die Wartezeit im Hafen**, nicht die Verspätung selbst (verpasste Anschlüsse, Reederkosten).
- Alle Zahlen sind **Größenordnungen aus einer Simulation, keine Messung an Echtdaten.**

## Design-Entscheidungen und Funde

**Zwei Stichproben statt einer.** Die Kostenkurve (15 Flotten × 2 Ziehungen je Verspätung, inklusive Hellsehen) braucht bei 9 Schiffen etwa 20 s und läuft deshalb auf Knopfdruck
mit Fortschrittsbalken. Mit nur 30 Szenarien blieb aber das Urteil „Neuplanung besser als starr" oft bei „kein klarer Unterschied" (−4,5 ± 2,4 h je Schiff). Deshalb rechnet die Demo beim
eingestellten δ zusätzlich automatisch eine **Fokus-Stichprobe** (30 Flotten × 3 Ziehungen, ohne Hellsehen, etwa 6 s, gecacht): Dort ist das Urteil klar. Bei gleichem δ steckt die kleinere Stichprobe Szenario für
Szenario in der größeren (gleiche Instanz- und Ziehungsnummern).

**Das Urteil kennt drei Zustände und nennt den Verlustanteil.** „Lohnt sich", „kostet mehr, als es bringt" und „kein klarer Unterschied": klar heißt gepaarte Differenz über mehr als zwei
Standardfehler. Jede Meldung nennt zusätzlich, in wie viel Prozent der Szenarien das Ergebnis schlechter ist, sowie Median gegen Mittel.

**Gemeinsame Zufallszahlen und zwei getrennte Zufallsströme.** Die Verspätungs-Seeds der Kurve sind für alle Verspätungen gleich (die Kurve wird glatter, die Strategien bleiben gepaart), und Schiffs-Seed und
Verspätungs-Seed sind getrennt: „Neue Verspätungen" ändert die Flotte nie und umgekehrt.

**Presets: typisch statt schön, und Stabilität an der Mittelwert-Aussage.** Aus der Stapelplanung ließ sich die Regel „die Aussage muss bei ≥ 90 % anderer Ziehungen halten" nicht übernehmen: Einzelne
Ziehungen halten die Geschichte je nach Preset nur bei 35 bis 100 %, denn die Neuplanung verliert im Einzelfall. Stattdessen: Bootstrap über 20 Ziehungen der gewählten Flotte (Mittelwert-Aussage in ≥ 90 % der
Neuziehungen), die gezeigte Ziehung erzählt die Geschichte und liegt zwischen dem 10. und 90. Perzentil. Alle Startwerte des Plans trugen die Kriterien schon, abgestimmt wurden nur Seeds.

**Fund: die Heuristik ist als „Hellsehen" ungeeignet.** Ein erster Ersatz durch die Einfüge-Heuristik auf den tatsächlichen Ankünften war in 6 von 72 Fällen schlechter als starr oder Neuplanung
(also keine untere Schranke). Deshalb der Exakt-Löser, und `actual_instance` verlängert den Planungshorizont, damit er auch bei großen Verspätungen eine Lösung findet.

**Fund: nichts kürzen, nichts drosseln.** Weniger Suchzüge in der Neuplanung (0 Züge: +5,3 h je Schiff schlechter als 40) und eine gedrosselte Neuplanung bei überfälligen Schiffen (−45 % Zeit,
aber +0,5 h je Schiff bei 12 h Verspätung) kosten Qualität; die identische, aber schnellere `replan_fast` (Präfix-Wiederverwendung, Kostenabbruch) bringt nur den Faktor 1,2.

**Beispiele nicht nach dem schönsten Fall.** Das Kai-Diagramm der Planungsseite zeigte zuerst den eindrucksvollsten Fall; gewählt wurde stattdessen die Ziehung, deren Unterschied dem Median über 40 Ziehungen
entspricht (Median-Gewinn 4 von 160 Gesamtkosten gegen ein Mittel von etwa 21). Die Presets folgen derselben Regel.

## Tests

`python -m pytest tests/ -v` – 304 Tests, rund 3 Minuten. Zusammensetzung:

- **Kern:** Rechts-Verschiebung gegen ein **unabhängiges Kontrollmodell** (stundenweise Ereignissimulation statt Vorgängerschleife); jede ausgeführte Belegung besteht `check_feasible` gegen die
  tatsächlichen Ankünfte; Invarianten je Neuplanungs-Ereignis (liegende Schiffe unverändert, Hindernisse respektiert, nichts in die Vergangenheit); `replan_fast` liefert bei 0, 1, 2, 5 und 40 Suchzügen
  exakt dasselbe wie die Referenz; feste Werte der Vorab-Messreihe (288 Einzelvergleiche ohne Abweichung).
- **Hellsehen:** Handfälle mit bekanntem Optimum, „Optimum ≤ jede Strategie", Zeitlimit-Pfade (nicht bewiesen, Rückfall auf die Heuristik, unzulässiger Plan wird abgelehnt).
- **Auswertung:** Kennzahlen, Verteilung besser/gleich/schlechter, Kipppunkt, Urteil in drei Zuständen, Kurve gegen Direktrechnungen (Szenario für Szenario).
- **Figuren und Panels:** Geometrie des Kai-Diagramms, Hover-Raster, gemeinsame Zeitachse, Farben (nichts fast Schwarzes für das dunkle Schema), Kennzahlen-Farben am Streamlit-Proto.
- **Presets:** je Preset ein Test am gewählten Seed-Paar, im Flotten-Mittel über 20 Ziehungen (Bootstrap), im Mittel über 40 Flotten × 3 Ziehungen für Mittel **und** Median.
- **PDF:** Inhalt Zelle für Zelle, genaue Sonderzeichen (fpdf2 stürzt bei „–" und „€" ab).
- **End-to-End (AppTest):** Skelett und Footer, jedes Preset, Permalink (Begrenzen, Einrasten, Round-Trip), Seeds, alle Regler an Min und Max, „passt nicht an den Kai", Kurve gültig oder veraltet, Exakt-Tab.

Zusätzlich wurde jedes Modul mit **eingebauten Fehlern** geprüft (über 250 Stück: Vorzeichen, Schwellen, Formeln, Seeds, Presets): Was die Tests nicht fanden, bekam einen eigenen Test; die verbleibenden
Überlebenden sind nachweislich gleichwertig (z. B. Toleranzvorzeichen, die nie erreicht werden).

## Dateistruktur

| Datei | Inhalt |
|---|---|
| `app.py` | Streamlit-Hauptablauf: Presets, Sidebar, Hauptansicht, Kai-Blick, Kernabschnitt, Methodenvergleich, Texte |
| `rb_constants.py` | Regler-Grenzen, `PRESETS`, Strategien, Farben, feste Hafenparameter, Referenz-Häfen der Messreihe |
| `rb_presets.py` | `SETTING_SPECS`, Permalink (Begrenzen und Einrasten), Presets, zwei Seed-Knöpfe, „passende Flotte suchen" |
| `rb_scenario.py` | Flotte aus den Reglerwerten, Prüfung „passt an den Kai" |
| `rb_delays.py` | Verspätungen (gleichmäßig / Ausreißer, eigener Zufallsstrom), tatsächliche Instanz, Puffer-Instanz |
| `rb_execution.py` | Rechts-Verschiebung, Puffer, Neuplanung (Ereignisse, Hindernisse, Prognose), Referenz- und schnelle Neuplanung |
| `rb_exact.py` | Hellsehen (CP-SAT), Zeitlimit und Kennzeichnung „nicht bewiesen", Preis der Unsicherheit |
| `rb_evaluation.py` | Strategien im Szenario, Kostenkurve, Fokus-Stichprobe, Verteilung, Kipppunkt, Urteil, Kennzahlen |
| `rb_visualization.py` | Kai-Diagramm, Kostenkurve, Verteilungsbalken, Vergleich (alle Achsen fest) |
| `rb_ui_panel.py` | Panel je Strategie und Exakt-Tab |
| `rb_pdf_export.py` | PDF-Ergebnis (`fpdf2`, Kernschrift, Sonderzeichen-Bereinigung) |
| `rb_stories.py` | Abnahmekriterien der Presets (Quelle für Werkzeug und Tests) |
| `berth_*.py` | wortgleiche Kopien der Kaiplatz-Zuteilung (Prüfsummen in `tests/test_copies.py`) |
| `tools/tune_presets.py`, `tools/PRESET_SWEEP.md` | Preset-Abstimmung und ihr Bericht |
| `tests/` | siehe oben |

## Bewusst nicht umgesetzt (mögliche Erweiterungen)

- **Verfrühung** und ein **Stabilitätspreis** (Strafe für Planänderungen) statt bloßer Zählung der Unruhe.
- **Kranzahl-abhängige Liegezeit** (siehe `quaycrane-demo`), Tiden, **mehrere Kaie**.
- **Echte AIS-Daten** für die Verspätungsverteilung.
- **Exakte Neuplanung als Schalter** im Einzelszenario (in der Vorab-Messung nur 1 bis 7 % besser).

## Verwandte Demos mit demselben mathematischen Modell

Verschiedene Themen im Portfolio teilen (fast) dasselbe Modell. Vor einer neuen Demo-Idee deshalb das
Modell vergleichen, nicht die Kulisse (Stand 2026-09-23):

- **Starrer Plan gegen reaktives Nachplanen unter Störung** ist ein wiederkehrendes Muster: `fahrzeugflotte-demo`,
  `robuste-kaiplatz-demo`, `blockzuweisung-demo` und `hofrobust-demo`. Der Twist von `hofrobust-demo`: am praktischen
  Minimum hängt der Sieger von der Störungsart ab (Ausfall: reaktiv klar besser, Fahrzeit-Rauschen: Münzwurf). Ideen wie
  robuste Touren bei unsicheren Standzeiten oder Same-Day-Aufträge im Nahverkehr (`vrp_demo`) wären das fünfte Exemplar
  und nur mit einem Hook jenseits von "reaktiv gewinnt" sinnvoll.

## Lokal ausführen

```bash
pip install -r requirements-dev.txt
streamlit run app.py
```

Tests: `python -m pytest tests/ -v`. Preset-Abstimmung: `python tools/tune_presets.py population|fleets|pick`.

---

Teil des [Operations-Research-Demo-Portfolios](https://sebastianhanisch.net/demos.html) von
[Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning.
Interesse an einer maßgeschneiderten Lösung? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html).
