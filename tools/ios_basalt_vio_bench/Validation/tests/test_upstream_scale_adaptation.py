"""The scale-adaptation table is the record of how upstream pixel-unit values
were carried to 1920x1440. These tests enforce that it stays a record and does
not decay into a list of tuned numbers."""

import json
import math
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
TABLE = (
    ROOT
    / "experiments/basalt_vio_phone_bench_2026-08-29/upstream_scale_adaptation.json"
)
CONTRACT = ROOT / "experiments/basalt_vio_phone_bench_2026-08-29/contract.json"

REQUIRED_PROVENANCE = {
    "engine",
    "parameter",
    "upstream_file",
    "upstream_commit",
    "original_value",
    "new_value",
    "scale_factor",
    "unit",
    "unit_evidence",
    "derivation",
}


@pytest.fixture(scope="module")
def table():
    return json.loads(TABLE.read_text())


@pytest.fixture(scope="module")
def contract():
    return json.loads(CONTRACT.read_text())


def test_target_matches_contract_scoring_resolution(table, contract):
    assert table["target_resolution"] == contract["live_soak"]["scoring_resolution"]


def test_every_resolved_entry_carries_full_provenance(table):
    missing = {}
    for entry in table["resolved"]:
        absent = REQUIRED_PROVENANCE - set(entry)
        if absent:
            missing[entry.get("parameter", "<unnamed>")] = sorted(absent)
    assert not missing, f"resolved entries missing provenance: {missing}"


def test_resolved_values_follow_their_stated_scale_factor(table):
    """A derivation that does not reproduce the new value is not a derivation."""
    for entry in table["resolved"]:
        expected = entry["original_value"] * entry["scale_factor"]
        assert math.isclose(entry["new_value"], expected, rel_tol=1e-9), (
            f"{entry['parameter']}: {entry['original_value']} x "
            f"{entry['scale_factor']} = {expected}, not {entry['new_value']}"
        )


def test_squared_units_use_the_squared_factor(table):
    """A squared length must scale by the square of the linear factor. Getting
    this wrong is silent: the value still looks plausible."""
    linear = table["scale_reference"]["basalt"]["linear_factor_by_height"]
    for entry in table["resolved"]:
        if entry["unit"].startswith("squared_"):
            assert math.isclose(entry["scale_factor"], linear**2, rel_tol=1e-9), (
                f"{entry['parameter']} is a squared unit but scales by "
                f"{entry['scale_factor']}, not {linear**2}"
            )
        elif entry["unit"].startswith("pixels"):
            assert math.isclose(entry["scale_factor"], linear, rel_tol=1e-9)


def test_basalt_grid_scaling_preserves_the_detection_cell_count(table):
    """The grid size sets the feature count: num_points_cell is 1, so the
    detector emits at most one keypoint per cell. Carrying it across must keep
    the tiling identical, or the tracked-set size changes with resolution."""
    grid = next(
        e
        for e in table["resolved"]
        if e["parameter"] == "config.optical_flow_detection_grid_size"
    )
    old_w, old_h = 640, 480
    new_w, new_h = table["target_resolution"]
    old_cells = (old_w // grid["original_value"]) * (old_h // grid["original_value"])
    new_cells = (new_w // grid["new_value"]) * (new_h // grid["new_value"])
    assert old_cells == new_cells, (
        f"grid {grid['original_value']} -> {grid['new_value']} changes the tiling "
        f"from {old_cells} to {new_cells} cells"
    )
    # And leaving it unscaled would have multiplied the tracked set.
    unscaled = (new_w // grid["original_value"]) * (new_h // grid["original_value"])
    assert unscaled > old_cells * 8


def test_unresolved_entries_state_why_and_how(table):
    for entry in table["unresolved"]:
        for field in ("problem", "why_not_guessed", "resolution_path"):
            assert entry.get(field), f"{entry['parameter']} lacks {field}"
        assert "new_value" not in entry, (
            f"{entry['parameter']} is listed unresolved but already carries a "
            "value; move it to resolved with a derivation or remove the value"
        )


def test_unresolved_entries_block_the_verdict(table):
    """While anything is unresolved the table must say so, so a 1920x1440
    verdict cannot be reported as if every parameter had been carried across."""
    if table["unresolved"]:
        assert table["status"] == "partial_blocking"
        assert table["blocks"], "unresolved parameters must block something"
    else:
        assert table["status"] == "complete"


def test_non_pixel_parameters_are_explicitly_excluded(table):
    """Counts, iteration limits, metric distances and IMU noise must never be
    scaled by an image factor. Listing them is what stops a later pass from
    sweeping them up."""
    excluded = {e["parameter"] for e in table["must_not_scale"]}
    for parameter in (
        "config.vio_max_states",
        "config.vio_max_kfs",
        "config.vio_min_triangulation_dist",
        "config.optical_flow_max_iterations",
        "imu.*",
    ):
        assert parameter in excluded
    for entry in table["must_not_scale"]:
        assert entry.get("reason")


def test_no_parameter_is_both_scaled_and_excluded(table):
    scaled = {e["parameter"] for e in table["resolved"]}
    scaled |= {e["parameter"] for e in table["unresolved"]}
    excluded = {e["parameter"] for e in table["must_not_scale"]}
    assert not (scaled & excluded)
