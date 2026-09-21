from berth_scenario import Instance, Ship, Zone, generate_instance


def _make_instance(quay_length=300, zones=None, safety_margin=10):
    zones = zones or (
        Zone(name="Tiefwasser", start=0, end=150, max_draft=15.0),
        Zone(name="Flachwasser", start=150, end=300, max_draft=9.0),
    )
    return Instance(quay_length=quay_length, zones=zones, ships=(), safety_margin=safety_margin, horizon=100)


def test_generate_instance_deterministic_given_seed():
    a = generate_instance(6, 600, 0.5, 15.0, 180, 0.25, 10.0, 0.2, 14, 0.3, 36, 0.3, 15, 7)
    b = generate_instance(6, 600, 0.5, 15.0, 180, 0.25, 10.0, 0.2, 14, 0.3, 36, 0.3, 15, 7)
    assert a.ships == b.ships


def test_generate_instance_ship_count_and_zone_coverage():
    inst = generate_instance(8, 500, 0.4, 14.0, 150, 0.2, 8.0, 0.2, 10, 0.2, 24, 0.3, 10, 1)
    assert len(inst.ships) == 8
    assert inst.zones[0].start == 0
    assert inst.zones[-1].end == inst.quay_length
    for z1, z2 in zip(inst.zones, inst.zones[1:]):
        assert z1.end == z2.start


def test_occupied_width_includes_safety_margin():
    inst = _make_instance(safety_margin=10)
    ship = Ship(index=0, name="S", length=50, draft=5.0, arrival=0, handling_time=5, priority="Tramp", weight=1.0)
    assert inst.occupied_width(ship) == 60


def test_feasible_start_ranges_excludes_incompatible_zone():
    inst = _make_instance()
    deep_ship = Ship(index=0, name="Deep", length=40, draft=12.0, arrival=0, handling_time=5, priority="Tramp", weight=1.0)
    ranges = inst.feasible_start_ranges(deep_ship)
    assert ranges == [(0, 150 - 50)]  # nur Tiefwasser (Flachwasser-Limit 9.0 < 12.0)


def test_feasible_start_ranges_ship_too_long_for_any_zone():
    inst = _make_instance()
    huge_ship = Ship(index=0, name="Huge", length=400, draft=5.0, arrival=0, handling_time=5, priority="Tramp", weight=1.0)
    assert inst.feasible_start_ranges(huge_ship) == []


def test_is_trivially_infeasible_true_when_one_ship_has_no_room():
    inst = _make_instance()
    ok_ship = Ship(index=0, name="OK", length=40, draft=5.0, arrival=0, handling_time=5, priority="Tramp", weight=1.0)
    huge_ship = Ship(index=1, name="Huge", length=400, draft=5.0, arrival=0, handling_time=5, priority="Tramp", weight=1.0)
    inst_ok = Instance(quay_length=inst.quay_length, zones=inst.zones, ships=(ok_ship,), safety_margin=10, horizon=100)
    inst_bad = Instance(
        quay_length=inst.quay_length, zones=inst.zones, ships=(ok_ship, huge_ship), safety_margin=10, horizon=100
    )
    assert inst_ok.is_trivially_infeasible() is False
    assert inst_bad.is_trivially_infeasible() is True


def test_generate_instance_presets_are_not_trivially_infeasible():
    import rb_constants as C  # in der berth-allocation-demo: berth_constants

    for name, p in C.REFERENCE_PRESETS.items():
        inst = generate_instance(
            p["n_ships"], p["quay_length"], p["deep_zone_fraction"], p["deep_draft_limit"],
            p["length_avg"], p["length_variability"], p["draft_avg"], p["draft_variability"],
            p["handling_avg"], p["handling_variability"], p["arrival_spread"], p["mainliner_fraction"],
            p["safety_margin"], p["seed"],
        )
        assert not inst.is_trivially_infeasible(), f"Preset '{name}' ist trivial unlösbar."
