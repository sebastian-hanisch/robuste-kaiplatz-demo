import pytest

import rb_constants as C
from berth_scenario import generate_instance
from rb_scenario import is_playable, make_instance, reference_instance, valid_reference_instances


def test_default_instance_is_the_full_quay_reference_port():
    assert make_instance() == generate_instance(**C.REFERENCE_PRESETS["Volle Kaikapazität"])


def test_port_is_fixed_and_only_the_fleet_parameters_change():
    a = make_instance(n_ships=6, quay_length=500, arrival_spread=20, handling_avg=10, mainliner_fraction=0.5, seed=3)
    assert len(a.ships) == 6 and a.quay_length == 500
    assert a.safety_margin == C.SAFETY_MARGIN
    assert a.zones[0].max_draft == C.DEEP_DRAFT_LIMIT
    assert a.zones[0].end == round(500 * C.DEEP_ZONE_FRACTION)
    assert max(s.arrival for s in a.ships) <= 20


def test_same_seed_same_instance_and_new_seed_new_fleet():
    assert make_instance(seed=5) == make_instance(seed=5)
    assert make_instance(seed=5).ships != make_instance(seed=6).ships


def test_every_parameter_has_an_effect():
    base = make_instance()
    for kw in (dict(n_ships=5), dict(quay_length=400), dict(arrival_spread=60), dict(handling_avg=20), dict(mainliner_fraction=0.6), dict(seed=8)):
        assert make_instance(**kw) != base, kw


def test_mainliner_fraction_is_a_fraction_not_a_percentage():
    assert all(s.priority != "Mainliner" for s in make_instance(n_ships=30, mainliner_fraction=0.0).ships)
    assert all(s.priority == "Mainliner" for s in make_instance(n_ships=30, mainliner_fraction=1.0).ships)


def test_is_playable_detects_a_ship_that_fits_no_zone():
    assert is_playable(make_instance())
    assert not is_playable(make_instance(quay_length=100, n_ships=5))   # Schiffe länger als der ganze Kai


def test_valid_reference_instances_only_yields_playable_ones_and_keeps_the_order():
    name = "Mainliner-Stoßzeit trifft Tiefwasser-Engpass"
    got = valid_reference_instances(name, range(30))
    assert got and all(is_playable(i) for i in got)
    assert got == [i for i in (reference_instance(name, s) for s in range(30)) if is_playable(i)]


@pytest.mark.parametrize("name", list(C.REFERENCE_PRESETS))
def test_reference_presets_are_playable_at_their_own_seed(name):
    assert is_playable(reference_instance(name, C.REFERENCE_PRESETS[name]["seed"]))
