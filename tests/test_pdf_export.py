import re

import pytest

import rb_constants as C
from rb_delays import scenario_delays
from rb_evaluation import run_strategies
from rb_pdf_export import generate_kai_pdf, pdf_text, short_name
from rb_presets import fleet_instance


def _settings(name="Große Verspätung", **override):
    p = dict(C.PRESETS[name])
    p.update(override)
    return p


def _pdf(name="Große Verspätung", compress=False, shares=(0.65, 0.16, 0.19), **override):
    s = _settings(name, **override)
    inst = fleet_instance(s["n_ships"], s["quay_length"], s["arrival_spread"], s["handling_avg"], s["mainliner_pct"], s["seed"])
    d = scenario_delays(inst, s["delay_mean"], s["delay_kind"], s["delay_seed"])
    outs = run_strategies(inst, d, s["delay_mean"], s["buffer"], s["forecast_pct"])
    return generate_kai_pdf(inst, outs, s, shares=shares, compress=compress), inst, outs, s


def _texts(data):
    """Alle Textstücke des (unkomprimierten) PDFs als Liste, Latin-1 gelesen, PDF-Escapes aufgelöst."""
    raw = re.findall(rb"\((.*?)\)\s*Tj", data)
    return [t.decode("latin-1").replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\") for t in raw]


# ---------- Sonderzeichen: mit den GENAUEN Zeichen testen (fpdf2 stürzt bei "–" und "€" ab) ----------
EXPECTED = {"–": "-", "—": "-", "€": "EUR", "σ": "Sigma", "δ": "Delta", "≥": ">=", "≤": "<=", "→": "->", "≈": "ca.", "„": '"', "“": '"', "’": "'",
            "·": "-", "▽": "v", "◆": "*", "±": "+-"}


@pytest.mark.parametrize("char,replacement", list(EXPECTED.items()))
def test_pdf_text_replaces_every_known_troublemaker_with_a_readable_equivalent(char, replacement):
    out = pdf_text(f"a{char}b")
    out.encode("latin-1")                                          # darf nicht werfen
    assert out == f"a{replacement}b"                               # nicht bloß "irgendwie ersetzt", sondern lesbar (kein "?")


def test_pdf_text_keeps_umlauts_and_times_sign():
    assert pdf_text("Füllgrad äöüß ÄÖÜ × 3") == "Füllgrad äöüß ÄÖÜ × 3"


def test_pdf_text_replaces_unknown_characters_and_emoji_instead_of_crashing():
    assert pdf_text("日本語").encode("latin-1") == b"???"
    assert "?" in pdf_text("⏱️ Starrer Plan")                      # Emoji würden den Kernfont sprengen: Kurznamen benutzen


def test_short_names_have_no_line_breaks_and_no_emoji():
    for key in C.STRATEGY_KEYS:
        name = short_name(key)
        assert "<br>" not in name and pdf_text(name) == name
    assert short_name(C.STRAT_PROGNOSE) == "Neuplanung + Prognose"


# ---------- Inhalt ----------
def test_pdf_is_a_valid_document_with_all_sections_and_the_scenario():
    data, inst, outs, s = _pdf()
    assert data.startswith(b"%PDF") and data.endswith(b"%%EOF\n") and len(data) > 2000
    for needle in ["Robuste Kaiplatzplanung", "Szenario", "Zusammenfassung", "Strategievergleich", "Schiffe", "Hinweise zum Modell", "Seed der Schiffe",
                   "Seed der Verspätungen", "Kailänge", "600 m", "Puffer", "100 % der mittleren Verspätung"]:
        needle = needle.encode("latin-1")                            # Umlaute stehen als Latin-1-Byte im Text
        assert needle in data, needle
    assert "12 h (gleichmäßig)" in _texts(data)                      # Klammern sind im PDF maskiert: über die Textstücke prüfen


def test_pdf_lists_every_strategy_with_its_numbers_and_delta_to_the_static_plan():
    data, inst, outs, s = _pdf()
    text = _texts(data)
    ref = outs[0].wait_total
    for o in outs:
        assert short_name(o.key) in text
        assert f"{o.wait_total:.0f}" in text and f"{o.wait_per_ship:.1f}" in text
        expected = "0" if abs(o.wait_total - ref) < 0.05 else f"{o.wait_total - ref:+.0f}"
        assert expected in text
    assert "Differenz (h)" in text


def test_pdf_ship_table_has_one_row_per_ship_with_eta_arrival_and_the_three_start_times():
    data, inst, outs, s = _pdf()
    text = _texts(data)
    by = {o.key: o.execution for o in outs}
    for ship in inst.ships:
        i = ship.index
        at = text.index(ship.name)
        assert text[at:at + 7] == [ship.name, ship.priority, str(ship.arrival), str(by[C.STRAT_STARR].arrivals[i]), str(by[C.STRAT_STARR].starts[i]),
                                   str(by[C.STRAT_NEU].starts[i]), str(by[C.STRAT_PROGNOSE].starts[i])]


def test_pdf_states_that_this_is_one_draw_and_quotes_the_shares_when_given():
    text = " ".join(_texts(_pdf(shares=(0.65, 0.16, 0.19))[0]))
    assert "EINE Ziehung" in text and "65 %" in text and "16 %" in text and "19 %" in text and "Mittelwert allein" in text
    plain = " ".join(_texts(_pdf(shares=None)[0]))
    assert "EINE Ziehung" in plain and "Mittelwert allein" not in plain


def test_pdf_scenario_values_follow_the_settings():
    data, inst, outs, s = _pdf("Ausreißer", buffer=3, forecast_pct=150, delay_seed=21)
    text = _texts(data)
    assert "8 h (Ausreißer)" in text and "3 h" in text and "150 % der mittleren Verspätung" in text and "21" in text
    assert str(s["n_ships"]) in text and f"{s['mainliner_pct']} %" in text


def test_pdf_reports_exact_seeds_and_sizes():
    data, inst, outs, s = _pdf("Ruhiger Hafen")
    text = _texts(data)
    assert "5" in text and "700 m" in text and "72 h" in text and "42" in text


@pytest.mark.parametrize("name", list(C.PRESETS))
def test_pdf_is_generated_for_every_preset_compressed_and_uncompressed(name):
    for compress in (True, False):
        data = _pdf(name, compress=compress)[0]
        assert data.startswith(b"%PDF") and len(data) > 1500


def test_pdf_without_any_delay_shows_zero_differences_and_no_crash():
    data, inst, outs, s = _pdf("Pünktlich")
    text = _texts(data)
    assert "0" in text and "0 h (gleichm\xe4\xdfig)" in text


def test_pdf_grows_with_the_fleet_and_stays_valid_at_the_limits():
    small = _pdf(n_ships=4)[0]
    large = _pdf(n_ships=10, quay_length=900)[0]
    assert len(large) > len(small)
    assert large.startswith(b"%PDF") and small.startswith(b"%PDF")


def _value_after(text, label):
    return text[text.index(label) + 1]


def test_pdf_scenario_block_pairs_every_label_with_its_own_value():
    data, inst, outs, s = _pdf("Ruhiger Hafen")
    text = _texts(data)
    assert _value_after(text, "Anzahl Schiffe") == "5" and _value_after(text, "Kailänge") == "700 m"
    assert _value_after(text, "Ankunftsfenster") == "72 h" and _value_after(text, "Ø Liegezeit") == "10 h"
    assert _value_after(text, "Anteil Mainliner") == "10 %" and _value_after(text, "Seed der Schiffe") == "42"
    assert _value_after(text, "Mittlere Verspätung") == "12 h (gleichmäßig)" and _value_after(text, "Seed der Verspätungen") == "3"
    assert _value_after(text, "Puffer") == "4 h" and _value_after(text, "Prognose") == "100 % der mittleren Verspätung"


def test_pdf_summary_quotes_the_signed_differences_to_the_static_plan():
    data, inst, outs, s = _pdf()
    text = _texts(data)
    base, neu, prog = outs[0], outs[2], outs[3]
    assert _value_after(text, "Starrer Plan (Referenz)") == f"{base.wait_per_ship:.1f} h Wartezeit je Schiff"
    assert _value_after(text, "Neuplanung") == f"{neu.wait_per_ship:.1f} h ({neu.wait_per_ship - base.wait_per_ship:+.1f} h gegen starr, {neu.replans} Neuplanungen)"
    assert _value_after(text, "Neuplanung + Prognose") == f"{prog.wait_per_ship:.1f} h ({prog.wait_per_ship - base.wait_per_ship:+.1f} h gegen starr)"


def test_pdf_strategy_table_rows_are_complete_and_in_column_order():
    data, inst, outs, s = _pdf()
    text = _texts(data)
    start = text.index("Differenz (h)") + 1
    ref = outs[0].wait_total
    for k, o in enumerate(outs):
        row = text[start + 6 * k: start + 6 * k + 6]
        delta = "0" if abs(o.wait_total - ref) < 0.05 else f"{o.wait_total - ref:+.0f}"
        assert row == [short_name(o.key), f"{o.wait_total:.0f}", f"{o.wait_per_ship:.1f}", str(o.replans), str(o.position_changes), delta], (k, row)
    assert text[start + 3] == "0" and text[start + 5] == "0"                                    # Referenz: keine Neuplanung, Differenz genau "0"


def test_pdf_quotes_the_shares_in_the_order_better_equal_worse():
    text = " ".join(_texts(_pdf(shares=(0.10, 0.20, 0.70))[0]))
    assert "in 10 % der Fälle besser, in 20 % gleich und in 70 % schlechter" in text
