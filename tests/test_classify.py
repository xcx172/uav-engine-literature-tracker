from __future__ import annotations

from src.classify import classify_record


def test_direct_requires_four_evidence():
    result = classify_record(
        "Aircraft two-stroke piston engine speed regulation",
        "An aircraft two-stroke piston engine speed regulation method is proposed.",
    )
    assert result.category == "direct"
    assert result.reason == "step4:direct"


def test_four_stroke_aircraft_with_two_stroke_comparison_is_near_aircraft():
    result = classify_record(
        "Speed control of a four-stroke aircraft piston engine",
        "The aircraft piston engine speed is controlled by a PI governor. "
        "A two-stroke engine was used for fuel consumption comparison.",
    )
    assert result.category == "near_aircraft"


def test_aircraft_without_piston_evidence_is_excluded():
    result = classify_record(
        "Aircraft engine speed control",
        "Aircraft engine speed control is studied with a governor.",
    )
    assert result.category == "excluded"


def test_non_aviation_two_stroke_is_near_two_stroke():
    result = classify_record(
        "Two-stroke engine speed regulation",
        "A two-stroke engine speed regulation method is proposed for racing engines.",
    )
    assert result.category == "near_two_stroke"


def test_rpm_test_condition_is_not_control_evidence():
    result = classify_record(
        "Combustion characteristics of a two-stroke engine",
        "Combustion tests were performed at 6000 rpm with a fixed throttle.",
    )
    assert result.category == "excluded"


def test_motor_comparison_does_not_change_aircraft_engine():
    result = classify_record(
        "Aircraft two-stroke piston engine speed regulation",
        "An aircraft two-stroke piston engine speed regulation method is proposed. "
        "A BLDC motor was used for comparison.",
    )
    assert result.category == "direct"


def test_motor_is_controlled_object():
    result = classify_record(
        "BLDC motor speed regulation",
        "The BLDC motor speed regulation is studied. An aircraft piston engine was used for comparison.",
    )
    assert result.category == "excluded"
    assert result.reason.startswith("step1")


def test_turbine_comparison_does_not_exclude_engine():
    result = classify_record(
        "Aircraft two-stroke piston engine speed regulation",
        "An aircraft two-stroke piston engine speed regulation method is proposed. "
        "A turboshaft engine was used for comparison.",
    )
    assert result.category == "direct"
