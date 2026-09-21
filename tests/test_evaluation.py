from berth_evaluation import check_feasible, evaluate
from berth_scenario import Instance, Ship, Zone

ZONES = (
    Zone(name="Tiefwasser", start=0, end=150, max_draft=15.0),
    Zone(name="Flachwasser", start=150, end=300, max_draft=9.0),
)


def _instance(ships, safety_margin=10):
    return Instance(quay_length=300, zones=ZONES, ships=ships, safety_margin=safety_margin, horizon=100)


def _ship(index, length=40, draft=5.0, arrival=0, handling_time=10, priority="Tramp", weight=1.0):
    return Ship(index=index, name=f"S{index}", length=length, draft=draft, arrival=arrival,
                handling_time=handling_time, priority=priority, weight=weight)


def test_check_feasible_accepts_non_overlapping_plan():
    s0, s1 = _ship(0), _ship(1)
    inst = _instance((s0, s1))
    plan = {0: (0, 0), 1: (0, 60)}  # zeitgleich, aber räumlich getrennt (>= 50 Breite je Schiff)
    ok, violations = check_feasible(inst, plan)
    assert ok, violations


def test_check_feasible_rejects_spatial_overlap_during_time_overlap():
    s0, s1 = _ship(0), _ship(1)
    inst = _instance((s0, s1))
    plan = {0: (0, 0), 1: (0, 30)}  # 30 < 50 (occupied_width) -> überlappt
    ok, violations = check_feasible(inst, plan)
    assert not ok
    assert any("überlappen" in v for v in violations)


def test_check_feasible_accepts_overlap_when_time_disjoint():
    s0, s1 = _ship(0, handling_time=5), _ship(1, handling_time=5)
    inst = _instance((s0, s1))
    plan = {0: (0, 0), 1: (5, 0)}  # gleiche Position, aber zeitlich disjunkt (halboffen)
    ok, violations = check_feasible(inst, plan)
    assert ok, violations


def test_check_feasible_rejects_start_before_arrival():
    s0 = _ship(0, arrival=10)
    inst = _instance((s0,))
    ok, violations = check_feasible(inst, {0: (5, 0)})
    assert not ok
    assert any("vor Ankunft" in v for v in violations)


def test_check_feasible_rejects_draft_exceeding_zone_limit():
    s0 = _ship(0, draft=12.0)
    inst = _instance((s0,))
    ok, violations = check_feasible(inst, {0: (0, 200)})  # Flachwasserzone, Limit 9.0 < 12.0
    assert not ok
    assert any("Tiefgang" in v for v in violations)


def test_check_feasible_rejects_missing_ship():
    s0, s1 = _ship(0), _ship(1)
    inst = _instance((s0, s1))
    ok, violations = check_feasible(inst, {0: (0, 0)})
    assert not ok


def test_evaluate_computes_wait_and_weighted_wait():
    s0 = _ship(0, arrival=5, weight=2.0)
    inst = _instance((s0,))
    result = evaluate(inst, {0: (12, 0)}, label="test")
    assert result["plan"][0]["wait"] == 7
    assert result["total_weighted_wait"] == 14.0
    assert result["total_wait"] == 7
    assert result["last_departure"] == 22  # start 12 + handling_time 10
