# Preset-Abstimmung (AP 6)

Reproduzierbar mit `./venv/Scripts/python.exe tools/tune_presets.py <modus>` (Modi: `population`, `fleets`, `pick`). Die Abnahmekriterien stehen in `rb_stories.py`
(einzige Quelle für Werkzeug und Tests), die Abnahme in `tests/test_preset_stories.py`.

**Grundsätze:** Seeds nicht nach dem schönsten Einzelfall wählen, sondern **typisch** (nahe an der Grundgesamtheit) und **rauschstabil**; Kriterien an der Grundgesamtheit
messen, für Mittel **und** Median (die Gewinne sind schief verteilt).

**Abweichung von der Stapelplanung:** Dort galt "die Aussage muss bei ≥ 90 % anderer Rausch-Ziehungen halten". Das lässt sich hier nicht übernehmen, denn die Demo zeigt
selbst, dass die Neuplanung in etwa jedem fünften Szenario verliert: Bei „Große Verspätung“ hält die Geschichte (Neuplanung ≤ starr und Prognose besser als Neuplanung) in einer
einzelnen Ziehung nur bei 40 bis 75 % der Ziehungen einer Flotte. Stabilität wird deshalb an der **Mittelwert-Aussage** gemessen: Bootstrap über die 20 Ziehungen einer Flotte
(300 Neuziehungen), Anteil der Neuziehungen, in denen alle Kriterien des Presets gelten, ≥ 90 %. Zusätzlich muss die **gezeigte Ziehung** die Geschichte erzählen und zwischen dem
10. und 90. Perzentil der Ziehungen der Flotte liegen (nicht der schönste Fall).

## 1. Grundgesamtheit je Preset (60 Flotten × 5 Ziehungen = 300 Szenarien)

Gewinn gegen starr in % der Kosten je Schiff (positiv = besser):

| Preset | starr (h je Schiff) | Puffer | Neuplanung | + Prognose | Kriterium | erfüllt |
|---|---|---|---|---|---|---|
| Pünktlich (δ 0) | 23,5 | −11,3 % | −0,8 % | −0,8 % | Puffer ≥ 5 % teurer; Neuplanung ±3 % | ja |
| Leichte Verspätung (δ 4) | 25,6 | −2,1 % | +5,7 % | +6,8 % | Puffer nicht besser; Neuplanung ≤ 10 % besser | ja |
| Große Verspätung (δ 12) | 32,7 | +1,4 % | +21,5 % | +37,1 % | Neuplanung ≥ 15 %; mit Prognose ≥ 30 % | ja |
| Ausreißer (δ 8, tail) | 43,0 | −3,3 % | +29,3 % | +52,1 % | Neuplanung ≥ 25 %; Median ≪ Mittel | ja |
| Ruhiger Hafen (δ 12, Puffer 4 h) | 6,5 | +14,2 % | +55,5 % | +73,4 % | Puffer besser; Neuplanung besser als Puffer | ja |

Die Startwerte des Plans (voller Hafen mit δ 0/4/12/8, ruhiger Hafen mit 5 Schiffen, Kai 700 m, Ankunftsfenster 72 h, Puffer 4 h) haben alle Kriterien schon getragen; abgestimmt
wurden nur die Seeds.

Verteilung (besser / gleich / schlechter gegen starr, Median- und Mittel-Gewinn der Neuplanung in gewichteten Wartestunden je Szenario):

| Preset | Neuplanung besser / gleich / schlechter | Median | Mittel | Anteil der besten 10 % am Gewinn |
|---|---|---|---|---|
| Pünktlich | 13 / 68 / 18 % | 0,0 | −1,7 | 96 % |
| Leichte Verspätung | 42 / 38 / 20 % | 0,0 | +13,1 | 63 % |
| Große Verspätung | 65 / 16 / 19 % | +29,8 | +63,2 | 50 % |
| Ausreißer | 57 / 31 / 12 % | +7,8 | +113,3 | 51 % |
| Ruhiger Hafen | 49 / 40 / 11 % | 0,0 | +17,9 | 55 % |

Beim Preset „Ausreißer“ liegt der Median-Gewinn (7,8) weit unter dem Mittel (113,3): wenige Szenarien tragen den Gewinn. Puffer bei „Pünktlich“: in 98 % der Szenarien schlechter als starr.

## 2. Gewählte Seeds (80 Kandidaten-Flotten × 20 Ziehungen je Preset)

Kandidaten müssen die Kriterien im Flotten-Mittel erfüllen und bootstrap-stabil (≥ 90 %) sein; unter ihnen die Flotte mit dem kleinsten Abstand zu den Gewinnen der Grundgesamtheit.
Die Verspätungs-Ziehung ist die, in der die Geschichte hält und der Gewinn der Neuplanung dem Median der Flotte am nächsten liegt.

| Preset | spielbare Flotten | erfüllen Kriterien | davon bootstrap-stabil | Flotte | Ziehung | Gewinne der Flotte (Puffer / Neuplanung / + Prognose) | Einzelziehungen der Flotte, in denen die Geschichte hält |
|---|---|---|---|---|---|---|---|
| Pünktlich | 65 | 49 | 49 | 14 | 3 (egal) | −11,3 / −1,5 / −1,5 % | 100 % |
| Leichte Verspätung | 65 | 55 | 38 | 56 | 6 | −2,0 / +5,9 / +7,4 % | 100 % |
| Große Verspätung | 65 | 27 | 7 | 14 | 14 | −0,1 / +25,1 / +41,2 % | 75 % |
| Ausreißer | 65 | 37 | 16 | 6 | 13 | −3,3 / +37,9 / +62,0 % | 90 % |
| Ruhiger Hafen | 78 | 24 | 14 | 42 | 3 | +15,5 / +58,7 / +71,4 % | 35 % |

Der Kai von 600 m macht rund 19 % der Zufallsflotten unspielbar (nur 65 von 80 Seeds spielbar bei 9 Schiffen), ein Schiff passt dann in keine Zone. Ruhiger Hafen: In vielen Flotten wartet bei 5 Schiffen
und 72 h Ankunftsfenster überhaupt niemand; die Geschichte „ein Puffer lohnt“ gilt deshalb nur in 24 von 78 Flotten, und in einer einzelnen Ziehung nur bei 35 %. Das Preset zeigt eine Flotte,
in der sie gilt (und die dem Mittel der Grundgesamtheit nahekommt: +15,5 % gegen +14,2 % für den Puffer).

## 3. Abnahmetests (`tests/test_preset_stories.py`)

- gezeigte Ziehung erzählt die Geschichte und liegt zwischen dem 10. und 90. Perzentil der Ziehungen der Flotte,
- Kriterien im Mittel der Flotte über 20 Ziehungen und bootstrap-stabil (≥ 90 %),
- Kriterien im Mittel über 40 Flotten × 3 Ziehungen, dazu Median gegen Mittel („Ausreißer“: Median ≤ halbes Mittel, obere 10 % > 40 % des Gewinns), schiefe Gewinne und Verlierer-Szenarien,
- Prognose bringt bei „Große Verspätung“ zusätzlich Wert (Anteil besser, Median, Mittel), Puffer kostet bei „Pünktlich“ in ≥ 90 % der Szenarien,
- Gewinn der Neuplanung auf der gewählten Flotte höchstens 12 Prozentpunkte neben dem der Grundgesamtheit.

Fehler-Einbau-Test: 11 geänderte Presets (falsche mittlere Verspätung bei drei Presets, Puffer 0 h, Verspätungsart vertauscht, extremste Ziehungen 8/11 bei „Große Verspätung“ und 15/6 bei „Ausreißer“, andere Flotte, voller statt ruhiger Hafen) werden alle erkannt.
