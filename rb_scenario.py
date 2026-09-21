"""Instanzen der robusten Kaiplatzplanung: fester Hafen, veränderliche Flotte (Fahrplan-Ankünfte = ETAs)."""

import rb_constants as C
from berth_scenario import generate_instance


def make_instance(n_ships=C.N_SHIPS_DEFAULT, quay_length=C.QUAY_LENGTH_DEFAULT, arrival_spread=C.ARRIVAL_SPREAD_DEFAULT,
                  handling_avg=C.HANDLING_AVG_DEFAULT, mainliner_fraction=C.MAINLINER_FRACTION_DEFAULT, seed=C.SEED_DEFAULT):
    """Instanz mit festem Hafen. `mainliner_fraction` als Bruchteil (0..1). Kann triviale Unlösbarkeit enthalten, siehe `is_playable`."""
    return generate_instance(
        n_ships=n_ships, quay_length=quay_length, deep_zone_fraction=C.DEEP_ZONE_FRACTION,
        deep_draft_limit=C.DEEP_DRAFT_LIMIT, length_avg=C.LENGTH_AVG, length_variability=C.LENGTH_VARIABILITY,
        draft_avg=C.DRAFT_AVG, draft_variability=C.DRAFT_VARIABILITY, handling_avg=handling_avg,
        handling_variability=C.HANDLING_VARIABILITY, arrival_spread=arrival_spread,
        mainliner_fraction=mainliner_fraction, safety_margin=C.SAFETY_MARGIN, seed=seed)


def is_playable(inst):
    """Nur solche Instanzen dürfen ausgeführt werden: passt ein Schiff in keine Zone, wirft die Einfüge-Heuristik einen Fehler."""
    return not inst.is_trivially_infeasible()


def reference_instance(name, seed):
    """Instanz eines Referenz-Hafens der Messreihe mit anderem Seed."""
    return generate_instance(**{**C.REFERENCE_PRESETS[name], "seed": seed})


def valid_reference_instances(name, seeds):
    out = []
    for seed in seeds:
        inst = reference_instance(name, seed)
        if is_playable(inst):
            out.append(inst)
    return out
