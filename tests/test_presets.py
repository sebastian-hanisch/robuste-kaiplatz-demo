import pytest

import rb_constants as C
import rb_presets as P
from rb_scenario import is_playable

FLEET_DEFAULT = (C.N_SHIPS_DEFAULT, C.QUAY_LENGTH_DEFAULT, C.ARRIVAL_SPREAD_DEFAULT, C.HANDLING_AVG_DEFAULT, C.MAINLINER_PCT_DEFAULT)


def test_every_setting_has_a_unique_url_parameter_and_a_default_inside_its_bounds():
    assert len({s.url_param for s in P.SETTING_SPECS.values()}) == len(P.SETTING_SPECS)
    for key, spec in P.SETTING_SPECS.items():
        if spec.lo is not None:
            assert spec.lo <= spec.default <= spec.hi, key
            assert P.bounds(key) == (spec.lo, spec.hi)


def test_default_values_are_on_the_step_grid():
    for key, spec in P.SETTING_SPECS.items():
        if spec.step and spec.lo is not None:
            assert (spec.default - spec.lo) % spec.step == 0, key


def test_preset_fields_match_the_state_keys_and_every_value_is_inside_the_bounds_and_on_the_grid():
    assert set(P.PRESET_STATE_KEYS.values()) == set(P.SETTING_SPECS)
    for name, preset in C.PRESETS.items():
        assert set(preset) == set(P.PRESET_STATE_KEYS), name
        for field, key in P.PRESET_STATE_KEYS.items():
            spec, value = P.SETTING_SPECS[key], preset[field]
            if spec.lo is None:
                assert value in C.DELAY_KINDS, (name, field)
            else:
                assert spec.lo <= value <= spec.hi, (name, field, value)
                if spec.step:
                    assert (value - spec.lo) % spec.step == 0, (name, field, value)     # sonst rastet der Regler beim Laden ein


def test_every_preset_fleet_is_playable_at_its_seed():
    for name, p in C.PRESETS.items():
        assert is_playable(P.fleet_instance(p["n_ships"], p["quay_length"], p["arrival_spread"], p["handling_avg"], p["mainliner_pct"], p["seed"])), name


def test_presets_keep_the_documented_story_structure():
    delay = {n: p["delay_mean"] for n, p in C.PRESETS.items()}
    assert delay["Pünktlich"] == 0 and delay["Leichte Verspätung"] < delay["Große Verspätung"]
    assert C.PRESETS["Ausreißer"]["delay_kind"] == "tail" and C.PRESETS["Große Verspätung"]["delay_kind"] == "exp"
    quiet = C.PRESETS["Ruhiger Hafen"]
    assert quiet["arrival_spread"] > C.PRESETS["Große Verspätung"]["arrival_spread"] and quiet["n_ships"] < C.PRESETS["Große Verspätung"]["n_ships"]


def test_preset_names_are_short_enough_for_three_buttons_per_row():
    assert len(C.PRESETS) == 5 and all(len(n) <= 20 for n in C.PRESETS)


# ---------------- Permalink ----------------
def test_parse_setting_clamps_to_the_range():
    spec = P.SETTING_SPECS["delay_mean_slider"]
    assert P.parse_setting(spec, "999") == 16 and P.parse_setting(spec, "-5") == 0 and P.parse_setting(spec, "7") == 7


def test_parse_setting_snaps_to_the_step():
    spec = P.SETTING_SPECS["forecast_slider"]
    assert P.parse_setting(spec, "47") == 50 and P.parse_setting(spec, "44") == 40 and P.parse_setting(spec, "200") == 200
    assert P.parse_setting(spec, "999") == 200                       # nie über die Obergrenze hinaus rasten
    quay = P.SETTING_SPECS["quay_length_slider"]
    assert P.parse_setting(quay, "614") == 610 and P.parse_setting(quay, "1000") == 900 and P.parse_setting(quay, "0") == 500
    assert P.parse_setting(P.SETTING_SPECS["mainliner_slider"], "33") == 35


def test_parse_setting_rejects_garbage():
    spec = P.SETTING_SPECS["buffer_slider"]
    for raw in ("abc", "", None, "nan", "1.5"):
        assert P.parse_setting(spec, raw) is None, raw


def test_delay_kind_is_parsed_as_a_string_and_only_known_values_pass():
    spec = P.SETTING_SPECS["delay_kind_radio"]
    assert P.parse_setting(spec, "tail") == "tail" and P.parse_setting(spec, "exp") == "exp"
    assert P.parse_setting(spec, "gauss") is None and P.parse_setting(spec, "1") is None
    assert spec.encoder("tail") == "tail" and P.SETTING_SPECS["buffer_slider"].encoder(3) == "3"


# ---------------- Seeds und Flotten ----------------
def test_fleet_instance_uses_percent_as_integer_and_matches_the_reference_port():
    a = P.fleet_instance(*FLEET_DEFAULT, C.SEED_DEFAULT)
    from berth_scenario import generate_instance
    assert a == generate_instance(**C.REFERENCE_PRESETS["Volle Kaikapazität"])
    assert P.fleet_instance(9, 600, 30, 14, 60, 7) != a


def test_next_playable_seed_finds_a_playable_one_after_start_and_wraps():
    fleet = (10, 500, 30, 14, 30)                                                    # nur etwa ein Drittel der Flotten passt
    s = P.next_playable_seed(fleet, 0)
    assert s is not None and s > 0 and is_playable(P.fleet_instance(*fleet, s))
    assert all(not is_playable(P.fleet_instance(*fleet, k)) for k in range(1, s))    # wirklich der NÄCHSTE
    lo, hi = C.SEED_RANGE
    wrapped = P.next_playable_seed(fleet, hi)
    assert wrapped is not None and lo <= wrapped <= hi and is_playable(P.fleet_instance(*fleet, wrapped))


def test_next_playable_seed_gives_up_when_no_fleet_fits():
    assert P.next_playable_seed((10, 500, 30, 14, 30), 0) is not None
    assert P.next_playable_seed((10, 500, 30, 14, 30), 5) != 5
    impossible = P.next_playable_seed((10, 100, 30, 14, 30), 0)
    assert impossible is None


# ---------------- Rand- und Zustandsfälle ----------------
def test_snapping_never_exceeds_the_upper_bound_even_if_the_bound_is_off_the_grid():
    spec = P.SettingSpec("x", int, 0, 0, 8, 3)                       # Raster 0, 3, 6, 9 - aber Obergrenze 8
    assert P.parse_setting(spec, "8") == 8 and P.parse_setting(spec, "7") == 6 and P.parse_setting(spec, "100") == 8


def test_query_params_are_written_as_plain_integers_or_the_kind_string(monkeypatch):
    written = {}
    monkeypatch.setattr(P.st, "query_params", written, raising=False)
    P.sync_query_params({"seed_input": 5.0, "delay_kind_radio": "tail", "forecast_slider": 100})
    assert written == {"seed": "5", "dk": "tail", "fc": "100"}


def test_sync_query_params_never_raises_when_the_address_bar_is_not_writable(monkeypatch):
    class Broken:
        def __setitem__(self, key, value):
            raise RuntimeError("nicht schreibbar")
    monkeypatch.setattr(P.st, "query_params", Broken(), raising=False)
    P.sync_query_params({"seed_input": 5})


def _state(fleet, seed):
    state = dict(zip(P.FLEET_KEYS, fleet))
    state["seed_input"] = seed
    return state


def test_find_playable_seed_takes_the_very_next_playable_seed(monkeypatch):
    fleet = (5, 700, 30, 14, 30)                                     # fast jede Flotte passt: der Nachfolger von 0 ist gleich der nächste
    assert is_playable(P.fleet_instance(*fleet, 1))
    state = _state(fleet, 0)
    monkeypatch.setattr(P.st, "session_state", state)
    P.find_playable_seed()
    assert state["seed_input"] == 1


def test_find_playable_seed_leaves_the_seed_when_nothing_fits(monkeypatch):
    state = _state((10, 100, 30, 14, 30), 42)
    monkeypatch.setattr(P.st, "session_state", state)
    P.find_playable_seed()
    assert state["seed_input"] == 42


def test_randomize_seed_only_sets_playable_fleets_and_falls_back_to_the_next_playable(monkeypatch):
    fleet = (10, 500, 30, 14, 30)
    state = _state(fleet, 5)
    monkeypatch.setattr(P.st, "session_state", state)
    for _ in range(20):
        P.randomize_seed()
        assert is_playable(P.fleet_instance(*fleet, state["seed_input"]))
    monkeypatch.setattr(P.random, "randint", lambda a, b: 3)         # würfelt immer denselben unspielbaren Seed
    bad = next(s for s in range(100) if not is_playable(P.fleet_instance(*fleet, s)))
    monkeypatch.setattr(P.random, "randint", lambda a, b: bad)
    state["seed_input"] = bad
    P.randomize_seed()
    assert state["seed_input"] != bad and is_playable(P.fleet_instance(*fleet, state["seed_input"]))
    assert state["seed_input"] == P.next_playable_seed(fleet, bad)


def test_randomize_delay_seed_changes_only_the_delay_seed(monkeypatch):
    state = _state((9, 600, 30, 14, 30), 7) | {"delay_seed_input": 3}
    monkeypatch.setattr(P.st, "session_state", state)
    monkeypatch.setattr(P.random, "randint", lambda a, b: 4321)
    P.randomize_delay_seed()
    assert state["delay_seed_input"] == 4321 and state["seed_input"] == 7
