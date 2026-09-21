"""Regler-Spezifikation, Permalink, Presets und Zufalls-Seed-Knöpfe (Standardmuster aus dem OR-Demo-Portfolio, siehe stk_presets.py).

Zwei getrennte Zufallsströme: der Seed der Schiffe (Flotte) und der Seed der Verspätungen. So ändert "Neue Verspätungen" die Flotte nie
und umgekehrt (Seed-Kopplungs-Falle aus früheren Demos)."""

import math
import random
from dataclasses import dataclass
from typing import Callable, Optional

import streamlit as st

import rb_constants as C
from rb_scenario import is_playable, make_instance


def _delay_kind(raw):
    if raw not in C.DELAY_KINDS:
        raise ValueError(raw)
    return raw


def _int_text(value):
    return str(int(value))


@dataclass(frozen=True)
class SettingSpec:
    url_param: str
    caster: Callable
    default: object
    lo: Optional[float] = None
    hi: Optional[float] = None
    step: Optional[int] = None
    encoder: Callable = _int_text


SETTING_SPECS = {
    "n_ships_slider": SettingSpec("ns", int, C.N_SHIPS_DEFAULT, *C.N_SHIPS_RANGE, 1),
    "quay_length_slider": SettingSpec("ql", int, C.QUAY_LENGTH_DEFAULT, *C.QUAY_LENGTH_RANGE, 10),
    "arrival_spread_slider": SettingSpec("as", int, C.ARRIVAL_SPREAD_DEFAULT, *C.ARRIVAL_SPREAD_RANGE, 1),
    "handling_avg_slider": SettingSpec("ha", int, C.HANDLING_AVG_DEFAULT, *C.HANDLING_AVG_RANGE, 1),
    "mainliner_slider": SettingSpec("ml", int, C.MAINLINER_PCT_DEFAULT, *C.MAINLINER_PCT_RANGE, 5),
    "seed_input": SettingSpec("seed", int, C.SEED_DEFAULT, *C.SEED_RANGE, 1),
    "delay_mean_slider": SettingSpec("dm", int, C.DELAY_MEAN_DEFAULT, *C.DELAY_MEAN_RANGE, 1),
    "delay_kind_radio": SettingSpec("dk", _delay_kind, C.DELAY_KIND_DEFAULT, encoder=str),
    "delay_seed_input": SettingSpec("dseed", int, C.DELAY_SEED_DEFAULT, *C.SEED_RANGE, 1),
    "buffer_slider": SettingSpec("bf", int, C.BUFFER_DEFAULT, *C.BUFFER_RANGE, 1),
    "forecast_slider": SettingSpec("fc", int, C.FORECAST_PCT_DEFAULT, *C.FORECAST_PCT_RANGE, C.FORECAST_PCT_STEP),
}

PRESET_STATE_KEYS = {
    "n_ships": "n_ships_slider", "quay_length": "quay_length_slider", "arrival_spread": "arrival_spread_slider",
    "handling_avg": "handling_avg_slider", "mainliner_pct": "mainliner_slider", "seed": "seed_input",
    "delay_mean": "delay_mean_slider", "delay_kind": "delay_kind_radio", "delay_seed": "delay_seed_input",
    "buffer": "buffer_slider", "forecast_pct": "forecast_slider",
}

# Regler, die die Flotte bestimmen (ohne Seed); die Verspätungen und Strategien gehören nicht dazu
FLEET_KEYS = ("n_ships_slider", "quay_length_slider", "arrival_spread_slider", "handling_avg_slider", "mainliner_slider")


def bounds(state_key):
    spec = SETTING_SPECS[state_key]
    return spec.lo, spec.hi


def parse_setting(spec, raw):
    """Wert aus der Adresszeile: umwandeln, auf den Bereich begrenzen, auf die Schrittweite runden. None, wenn er sich nicht auswerten lässt."""
    try:
        value = spec.caster(raw)
    except (ValueError, TypeError):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if spec.lo is not None:
        value = max(spec.lo, value)
    if spec.hi is not None:
        value = min(spec.hi, value)
    if spec.step and spec.step > 1 and spec.lo is not None:
        value = spec.lo + round((value - spec.lo) / spec.step) * spec.step
        value = min(spec.hi, value)
    return value


def init_session_state_defaults():
    for state_key, spec in SETTING_SPECS.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = spec.default


def load_permalink_settings():
    if "permalink_loaded" in st.session_state:
        return
    qp = st.query_params
    for state_key, spec in SETTING_SPECS.items():
        if spec.url_param in qp:
            value = parse_setting(spec, qp[spec.url_param])
            if value is not None:
                st.session_state[state_key] = value
    st.session_state["permalink_loaded"] = True


def sync_query_params(values):
    """values: dict state_key -> aktueller Wert (aus den Widgets, damit dieselbe Änderung, die gerade gerendert wurde, sofort in der Adresszeile landet)."""
    try:
        for state_key, value in values.items():
            st.query_params[SETTING_SPECS[state_key].url_param] = SETTING_SPECS[state_key].encoder(value)
    except Exception:
        pass


def apply_preset(name):
    for field, state_key in PRESET_STATE_KEYS.items():
        st.session_state[state_key] = C.PRESETS[name][field]


# ---------------------------------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------------------------------
def fleet_instance(n_ships, quay_length, arrival_spread, handling_avg, mainliner_pct, seed):
    """Instanz aus den Reglerwerten (Prozent als ganze Zahl, Umrechnung hier)."""
    return make_instance(int(n_ships), int(quay_length), int(arrival_spread), int(handling_avg), int(mainliner_pct) / 100, int(seed))


def next_playable_seed(fleet, start):
    """Nächster Seed ab `start` (aufsteigend, mit Umlauf im Bereich), bei dem jedes Schiff der Flotte an den Kai passt; None, wenn keiner in Reichweite.
    `fleet`: (n_ships, quay_length, arrival_spread, handling_avg, mainliner_pct)."""
    lo, hi = C.SEED_RANGE
    span = hi - lo + 1
    for k in range(1, 401):
        seed = lo + (start - lo + k) % span
        if is_playable(fleet_instance(*fleet, seed)):
            return seed
    return None


def _fleet_from_state():
    return tuple(st.session_state[k] for k in FLEET_KEYS)


def randomize_seed():
    """Würfelt einen neuen Schiffs-Seed, dessen Flotte an den Kai passt (unspielbare Würfe werden übersprungen)."""
    fleet = _fleet_from_state()
    for _ in range(200):
        seed = random.randint(*C.SEED_RANGE)
        if is_playable(fleet_instance(*fleet, seed)):
            st.session_state["seed_input"] = seed
            return
    found = next_playable_seed(fleet, st.session_state["seed_input"])
    if found is not None:
        st.session_state["seed_input"] = found


def find_playable_seed():
    """Für den Hinweis "passt nicht an den Kai": nächsten passenden Seed übernehmen."""
    found = next_playable_seed(_fleet_from_state(), st.session_state["seed_input"])
    if found is not None:
        st.session_state["seed_input"] = found


def randomize_delay_seed():
    st.session_state["delay_seed_input"] = random.randint(*C.SEED_RANGE)
