"""PDF-Export des Ergebnisses (fpdf2, Helvetica-Kernschrift, nur Text und Tabellen).

Die Kernschriften kennen nur Latin-1: Umlaute und "×" sind erlaubt, aber "–" (Gedankenstrich), "€", "σ", "≥", Emoji usw.
lassen fpdf2 abstürzen. Deshalb läuft jeder Text durch pdf_text(); Strategien erscheinen mit ihren Kurznamen ohne Emoji.
"""

import time

import rb_constants as C
from rb_evaluation import comparison_rows, outcome_of

_REPLACEMENTS = {
    "–": "-", "—": "-", "‑": "-", "σ": "Sigma", "δ": "Delta", "≥": ">=", "≤": "<=", "→": "->", "≈": "ca.", "€": "EUR",
    "·": "-", "“": '"', "”": '"', "„": '"', "’": "'", "‘": "'", "▽": "v", "◆": "*", "±": "+-",
}


def pdf_text(text):
    """Text für die Helvetica-Kernschrift: bekannte Sonderzeichen ersetzen, den Rest Latin-1-sicher machen."""
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def short_name(key):
    return C.STRATEGY_SHORT[key].replace("<br>", " ")


def generate_kai_pdf(inst, outcomes, settings, shares=None, compress=True):
    """Ergebnis der aktuellen Einstellung als PDF: Szenario, Zusammenfassung, Strategievergleich, Schiffe, Hinweise.

    `settings`: dict mit den Reglerwerten (n_ships, quay_length, arrival_spread, handling_avg, mainliner_pct, seed, delay_mean, delay_kind, delay_seed,
    buffer, forecast_pct). `shares`: optional (besser, gleich, schlechter) der Neuplanung gegen starr über viele Szenarien (Anteile 0..1) für den
    Hinweis, dass dies EINE Ziehung ist."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    baseline = outcome_of(outcomes, C.STRAT_STARR)
    replanned = outcome_of(outcomes, C.STRAT_NEU)
    forecast = outcome_of(outcomes, C.STRAT_PROGNOSE)

    pdf = FPDF()
    pdf.set_compression(compress)
    pdf.add_page()

    def line(text, height=7, width=0):
        pdf.cell(width, height, pdf_text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def heading(text):
        pdf.set_font("Helvetica", "B", 12)
        line(text, 8)
        pdf.set_font("Helvetica", "", 10)

    def pairs(rows):
        for label, value in rows:
            pdf.cell(70, 6, pdf_text(label), border=0)
            line(value, 6)

    def table(headers, widths, rows):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(230, 230, 230)
        for header, width in zip(headers, widths):
            pdf.cell(width, 7, pdf_text(header), border=1, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(7)
        pdf.set_font("Helvetica", "", 9)
        for row in rows:
            for value, width in zip(row, widths):
                pdf.cell(width, 7, pdf_text(str(value)), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.ln(7)

    pdf.set_font("Helvetica", "B", 16)
    line("Robuste Kaiplatzplanung: Puffer oder Information?", 10)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 120, 120)
    line(f"Erstellt: {time.strftime('%d.%m.%Y %H:%M')}  -  sebastianhanisch.net", 6)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    s = settings
    heading("Szenario")
    pairs([
        ("Anzahl Schiffe", str(s["n_ships"])),
        ("Kailänge", f"{s['quay_length']} m"),
        ("Ankunftsfenster", f"{s['arrival_spread']} h"),
        ("Ø Liegezeit", f"{s['handling_avg']} h"),
        ("Anteil Mainliner", f"{s['mainliner_pct']} %"),
        ("Seed der Schiffe", str(s["seed"])),
        ("Mittlere Verspätung", f"{s['delay_mean']} h ({C.DELAY_KIND_LABELS[s['delay_kind']]})"),
        ("Seed der Verspätungen", str(s["delay_seed"])),
        ("Puffer", f"{s['buffer']} h"),
        ("Prognose", f"{s['forecast_pct']} % der mittleren Verspätung"),
    ])
    pdf.ln(3)

    heading("Zusammenfassung")
    pairs([
        ("Starrer Plan (Referenz)", f"{baseline.wait_per_ship:.1f} h Wartezeit je Schiff"),
        ("Neuplanung", f"{replanned.wait_per_ship:.1f} h ({replanned.wait_per_ship - baseline.wait_per_ship:+.1f} h gegen starr, {replanned.replans} Neuplanungen)"),
        ("Neuplanung + Prognose", f"{forecast.wait_per_ship:.1f} h ({forecast.wait_per_ship - baseline.wait_per_ship:+.1f} h gegen starr)"),
    ])
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(110, 110, 110)
    if shares is not None:
        better, equal, worse = shares
        note = (f"Das ist EINE Ziehung der Verspätungen. Über viele Szenarien mit diesen Einstellungen ist die Neuplanung in {better * 100:.0f} % der Fälle besser, "
                f"in {equal * 100:.0f} % gleich und in {worse * 100:.0f} % schlechter als der starre Plan: Der Mittelwert allein täuscht.")
    else:
        note = "Das ist EINE Ziehung der Verspätungen; ein Einzelfall kann vom Mittel über viele Szenarien deutlich abweichen."
    pdf.multi_cell(0, 5, pdf_text(note), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    heading("Strategievergleich")
    rows = []
    for r in comparison_rows(outcomes):
        rows.append([short_name(r.key), f"{r.wait_total:.0f}", f"{r.wait_per_ship:.1f}", r.replans, r.position_changes,
                     "0" if abs(r.delta_vs_baseline) < 0.05 else f"{r.delta_vs_baseline:+.0f}"])
    table(["Strategie", "Wartezeit gewichtet (h)", "je Schiff (h)", "Neuplanungen", "Positionswechsel", "Differenz (h)"], [40, 42, 26, 30, 32, 20], rows)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(110, 110, 110)
    line("Differenz = gewichtete Wartezeit dieser Strategie minus starrer Plan (negativ = besser). Die Wartezeit zählt ab der tatsächlichen Ankunft.", 5)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    heading("Schiffe")
    ships = []
    for ship in inst.ships:
        i = ship.index
        ships.append([ship.name, ship.priority, ship.arrival, baseline.execution.arrivals[i],
                      baseline.execution.starts[i], replanned.execution.starts[i], forecast.execution.starts[i]])
    table(["Schiff", "Klasse", "ETA (h)", "Ankunft (h)", "Start starr", "Start Neuplanung", "Start + Prognose"], [24, 26, 20, 26, 26, 34, 34], ships)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(110, 110, 110)
    line("Zeiten in Stunden ab Beginn des Planungszeitraums. ETA = Fahrplan-Ankunft, Ankunft = tatsächliche Ankunft.", 5)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    heading("Hinweise zum Modell")
    pdf.set_font("Helvetica", "", 9)
    for note in [
        "Nur Verspätungen, keine Verfrühung; feste Liegezeit; ein Kai mit zwei Tiefenzonen; die Wartezeit ist nach Klasse gewichtet (Mainliner 3, Feeder 1,5, Tramp 1).",
        "Die Neuplanung ist kostenlos und sofort umsetzbar; Lotsen, Schlepper und Mannschaften sind nicht modelliert. Die Unruhe im Plan wird gezählt, nicht bepreist.",
        "Die Verspätungsverteilungen sind Annahmen, keine Echtdaten: gleichmäßig (exponentialverteilt) oder Ausreißer (80 % pünktlich, 20 % sehr spät) bei gleichem Mittelwert.",
        "Alle Zahlen sind Größenordnungen aus einer Simulation, keine Messung an Echtdaten.",
    ]:
        pdf.multi_cell(0, 5, pdf_text("- " + note), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())
