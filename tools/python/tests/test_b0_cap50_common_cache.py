from __future__ import annotations

import copy
import hashlib
import json
import struct
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import b0_cap50_common_cache as C
import b0_prepare_eval as E
import b0_preregister as P


def _w2c(center=(0.0, 0.0, 0.0)) -> np.ndarray:
    out = np.eye(4, dtype=np.float64)
    out[:3, 3] = -np.asarray(center, dtype=np.float64)
    return out


def test_ordered_hash_encodings_match_frozen_contract() -> None:
    names = ["b.jpg", "a.jpg"]
    expected = hashlib.sha256(b"b.jpg\na.jpg\n").hexdigest()
    assert C.ordered_names_sha256(names) == expected

    by_name = {
        "a.jpg": {"sha256": "1" * 64, "size_bytes": 7},
        "b.jpg": {"sha256": "2" * 64, "size_bytes": 9},
    }
    payload = f"b.jpg\t{'2' * 64}\t9\na.jpg\t{'1' * 64}\t7\n".encode()
    assert C.image_root_manifest_sha256(names, by_name) == hashlib.sha256(payload).hexdigest()


def test_cap50_order_hash_constants_are_the_preregistered_cohort() -> None:
    assert (
        C.FROZEN_CAP50_FRAME_ORDER_SHA256
        == "b632e81a048b1de96d36539e2edab67b0a721f7447d0392369cf2f96cf500c61"
    )
    assert (
        C.FROZEN_CAP50_RECONSTRUCTION_ORDER_SHA256
        == "8ef00f3b310ed5d3c0ee00ff49f92e46cdfbadf703faec23e46a203367822666"
    )
    assert (
        C.FROZEN_CAP50_HELDOUT_ORDER_SHA256
        == "2cf47fa3fcdb329711f762bfd360668158d3fb5915d7fd754bdfc2d6df577980"
    )


def _synthetic_cap50_names() -> tuple[list[str], list[str], list[str]]:
    names = [f"synthetic_{index:03d}_tap-{1000 + index}.jpg" for index in range(115)]
    reconstruction_indices, heldout_indices = C.frozen_split(115)
    reconstruction = [names[index] for index in reconstruction_indices]
    heldout = [names[index] for index in heldout_indices]
    return names, reconstruction, heldout


def _patch_frozen_cohort_to_fixture(
    monkeypatch: pytest.MonkeyPatch,
    names: list[str],
    reconstruction: list[str],
    heldout: list[str],
) -> None:
    monkeypatch.setattr(C, "FROZEN_CAP50_FRAME_ORDER_SHA256", C.ordered_names_sha256(names))
    monkeypatch.setattr(
        C,
        "FROZEN_CAP50_RECONSTRUCTION_ORDER_SHA256",
        C.ordered_names_sha256(reconstruction),
    )
    monkeypatch.setattr(
        C,
        "FROZEN_CAP50_HELDOUT_ORDER_SHA256",
        C.ordered_names_sha256(heldout),
    )


def test_self_consistent_alternate_115_frame_cohort_is_rejected() -> None:
    names, reconstruction, heldout = _synthetic_cap50_names()
    with pytest.raises(C.ContractError, match="frozen cap50 ordered cohort hash mismatch"):
        C.require_frozen_cap50_cohort(names, reconstruction, heldout)


@pytest.mark.parametrize("mutated_role", ["all", "reconstruction", "heldout"])
def test_frozen_cap50_cohort_rejects_each_order_hash_mutation(
    monkeypatch: pytest.MonkeyPatch, mutated_role: str
) -> None:
    names, reconstruction, heldout = _synthetic_cap50_names()
    _patch_frozen_cohort_to_fixture(monkeypatch, names, reconstruction, heldout)
    assert C.require_frozen_cap50_cohort(names, reconstruction, heldout) == {
        "frame_order_sha256": C.ordered_names_sha256(names),
        "reconstruction_order_sha256": C.ordered_names_sha256(reconstruction),
        "heldout_order_sha256": C.ordered_names_sha256(heldout),
    }

    mutated = {
        "all": list(names),
        "reconstruction": list(reconstruction),
        "heldout": list(heldout),
    }
    mutated[mutated_role][0], mutated[mutated_role][1] = (
        mutated[mutated_role][1],
        mutated[mutated_role][0],
    )
    with pytest.raises(C.ContractError, match="frozen cap50 ordered cohort hash mismatch"):
        C.require_frozen_cap50_cohort(
            mutated["all"], mutated["reconstruction"], mutated["heldout"]
        )


def test_scale_intrinsics_is_axis_specific() -> None:
    K = np.array([[800.0, 0.0, 500.0], [0.0, 810.0, 280.0], [0.0, 0.0, 1.0]])
    got = C.scale_intrinsics(K, source_wh=(1024, 576), target_wh=(896, 512))
    np.testing.assert_allclose(got[0], K[0] * (896 / 1024))
    np.testing.assert_allclose(got[1], K[1] * (512 / 576))
    np.testing.assert_array_equal(got[2], np.array([0.0, 0.0, 1.0]))
    assert got.dtype == np.float32


def test_decode_arkit_extrinsic_to_opencv_w2c() -> None:
    c2w_arkit = np.eye(4)
    c2w_arkit[:3, 3] = [1.0, 2.0, 3.0]
    flat = c2w_arkit.T.reshape(-1).tolist()
    got = C.decode_arkit_extrinsic_to_w2c(flat)
    expected_c2w_cv = np.eye(4)
    expected_c2w_cv[:3, :3] = np.diag([1.0, -1.0, -1.0])
    expected_c2w_cv[:3, 3] = [1.0, 2.0, 3.0]
    np.testing.assert_allclose(got, np.linalg.inv(expected_c2w_cv), atol=1e-12)


def test_sfm_quaternion_wxyz_is_decoded_as_world_to_camera_rotation() -> None:
    got = C.quaternion_wxyz_to_rotation([1.0, 0.0, 0.0, 0.0])
    np.testing.assert_allclose(got, np.eye(3), atol=1e-12)
    half = np.sqrt(0.5)
    got_z90 = C.quaternion_wxyz_to_rotation([half, 0.0, 0.0, half])
    np.testing.assert_allclose(got_z90 @ [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], atol=1e-12)


def test_visible_sparse_points_and_depth_range_are_input_only() -> None:
    K = np.array([[100.0, 0.0, 50.0], [0.0, 100.0, 50.0], [0.0, 0.0, 1.0]])
    visible_points = [[0.01 * i, 0.0, 1.0 + 0.2 * i] for i in range(10)]
    points = np.array([*visible_points, [9.0, 0.0, 1.0], [0.0, 0.0, -1.0]], dtype=np.float64)
    visible, z = C.visible_sparse_points(points, K, np.eye(4), image_wh=(100, 100))
    np.testing.assert_array_equal(visible, [*[True] * 10, False, False])
    dmin, dmax, count = C.input_depth_range(points, visible, z)
    assert count == 10
    assert 0.1 <= dmin < 1.0
    assert dmax > 3.0


def test_source_selection_requires_shared_sparse_support_and_obeys_baseline() -> None:
    visibility = np.array(
        [
            [1, 1, 1, 1, 1, 1, 1, 0],
            [1, 1, 1, 1, 1, 0, 0, 0],
            [1, 1, 1, 1, 1, 1, 1, 0],
            [1, 1, 1, 1, 1, 0, 0, 1],
            [1, 1, 1, 1, 1, 1, 1, 1],
        ],
        dtype=bool,
    )
    points = np.array([[0.05 * i, 0.0, 2.0] for i in range(8)], dtype=np.float64)
    centers = np.array([[0, 0, 0], [0.01, 0, 0], [0.2, 0, 0], [0.3, 0, 0], [0.4, 0, 0]], float)
    got, rows = C.select_sources_for_ref(
        0,
        visibility,
        points,
        centers,
        np.repeat(np.eye(4, dtype=np.float64)[None], 5, axis=0),
        ["r", "near", "best", "weak", "wide"],
        k=2,
        min_baseline_m=0.06,
        metres_per_model_unit=1.0,
        candidate_indices=[1, 2, 3, 4],
    )
    assert "near" not in got
    assert got[0] == "weak"
    assert len(got) == 2
    assert all(row["baseline_m"] >= 0.06 for row in rows if row["selected"])


def test_source_selection_applies_max_baseline_forward_angle_and_frozen_score() -> None:
    visibility = np.ones((6, 6), dtype=bool)
    points = np.array([[0.02 * i, 0.0, 2.0] for i in range(6)], dtype=np.float64)
    centers = np.array(
        [[0, 0, 0], [0.05, 0, 0], [0.10, 0, 0], [0.25, 0, 0], [0.30, 0, 0], [1.51, 0, 0]],
        dtype=np.float64,
    )
    poses = np.repeat(np.eye(4, dtype=np.float64)[None], 6, axis=0)
    angle = np.deg2rad(46.0)
    # OpenCV camera forward in world is R.T @ +Z.  This pose is outside 45 degrees.
    poses[4, :3, :3] = np.array(
        [[np.cos(angle), 0.0, -np.sin(angle)], [0.0, 1.0, 0.0], [np.sin(angle), 0.0, np.cos(angle)]]
    )
    got, rows = C.select_sources_for_ref(
        0,
        visibility,
        points,
        centers,
        poses,
        ["ref", "too_near", "valid_10cm", "ideal_25cm", "turned", "too_far"],
        k=2,
        metres_per_model_unit=1.0,
        candidate_indices=[1, 2, 3, 4, 5],
    )
    assert got == ["ideal_25cm", "valid_10cm"]
    assert [row["baseline_m"] for row in rows] == pytest.approx([0.25, 0.10])
    assert all(row["forward_angle_deg"] <= 45.0 for row in rows)
    assert rows[0]["selection_score"] == pytest.approx(0.0)
    assert rows[1]["selection_score"] == pytest.approx(abs(np.log(0.10 / 0.25)))


def test_source_selection_score_tie_is_broken_by_canonical_source_order() -> None:
    visibility = np.ones((3, 5), dtype=bool)
    points = np.array([[0.01 * i, 0.0, 2.0] for i in range(5)], dtype=np.float64)
    centers = np.array([[0, 0, 0], [0.125, 0, 0], [0.5, 0, 0]], dtype=np.float64)
    poses = np.repeat(np.eye(4, dtype=np.float64)[None], 3, axis=0)
    got, _ = C.select_sources_for_ref(
        0,
        visibility,
        points,
        centers,
        poses,
        ["ref", "first", "second"],
        k=2,
        metres_per_model_unit=1.0,
        candidate_indices=[2, 1],
    )
    assert got == ["first", "second"]


def test_l1dp_v1_parser_and_numerical_comparison(tmp_path: Path) -> None:
    depth = np.array([[1.0, 2.0], [4.0, 8.0]], dtype="<f4")
    confidence = np.array([[0.1, 0.2], [0.3, 0.4]], dtype="<f4")
    path = tmp_path / "l1_depth_20.bin"
    path.write_bytes(
        struct.pack("<4sIIII", b"L1DP", 1, 20, 2, 2)
        + depth.tobytes()
        + confidence.tobytes()
    )
    loaded_depth, loaded_confidence, identity = C.load_l1dp_v1(
        path, expected_frame_id=20, expected_hw=(2, 2)
    )
    np.testing.assert_array_equal(loaded_depth, depth)
    np.testing.assert_array_equal(loaded_confidence, confidence)
    assert identity["magic"] == "L1DP"
    assert identity["version"] == 1
    assert identity["frame_id"] == 20

    metrics = C.compare_raw_to_production_l1dp(
        depth * np.float32(1.1), confidence + np.float32(0.05), loaded_depth, loaded_confidence
    )
    assert metrics["finite_positive_overlap_count"] == 4
    assert metrics["finite_positive_overlap_fraction"] == pytest.approx(1.0)
    assert metrics["depth_absrel"]["mean"] == pytest.approx(0.1, abs=1e-6)
    assert metrics["depth_absrel"]["median"] == pytest.approx(0.1, abs=1e-6)
    assert metrics["confidence_abs_delta"]["max"] == pytest.approx(0.05, abs=1e-6)


def test_l1dp_parser_rejects_wrong_header_or_size(tmp_path: Path) -> None:
    path = tmp_path / "bad.bin"
    path.write_bytes(struct.pack("<4sIIII", b"NOPE", 1, 20, 2, 2) + b"\0" * 32)
    with pytest.raises(C.ContractError, match="magic"):
        C.load_l1dp_v1(path, expected_frame_id=20, expected_hw=(2, 2))
    path2 = tmp_path / "short.bin"
    path2.write_bytes(struct.pack("<4sIIII", b"L1DP", 1, 20, 2, 2) + b"\0" * 28)
    with pytest.raises(C.ContractError, match="byte size"):
        C.load_l1dp_v1(path2, expected_frame_id=20, expected_hw=(2, 2))


def test_repeat_prediction_must_be_bit_identical() -> None:
    depth = np.ones((2, 2), np.float32)
    confidence = np.full((2, 2), 0.5, np.float32)
    evidence = C.require_bit_identical_repeat(depth, confidence, depth.copy(), confidence.copy())
    assert evidence["depth_bit_identical"] is True
    assert evidence["confidence_bit_identical"] is True
    changed = depth.copy()
    changed[0, 0] = np.nextafter(changed[0, 0], np.float32(2.0))
    with pytest.raises(C.ContractError, match="not bit-identical"):
        C.require_bit_identical_repeat(depth, confidence, changed, confidence.copy())


def test_projection_pyramid_matches_five_view_coreml_contract() -> None:
    Ks = np.repeat(np.eye(3, dtype=np.float32)[None], 5, axis=0)
    Ks[:, 0, 0] = 800
    Ks[:, 1, 1] = 810
    w2c = np.repeat(np.eye(4, dtype=np.float32)[None], 5, axis=0)
    out = C.build_projection_pyramid(Ks, w2c)
    assert set(out) == {"p1", "p2", "p3", "p4"}
    assert all(value.shape == (1, 5, 2, 4, 4) for value in out.values())
    assert out["p1"][0, 0, 1, 0, 0] == pytest.approx(100.0)
    assert out["p4"][0, 0, 1, 0, 0] == pytest.approx(800.0)


def _frozen_output_contract() -> dict[str, object]:
    return C.resolve_frozen_coreml_output_contract(
        model_tree_sha256=C.FROZEN_COREML_MODEL_TREE_SHA256,
        spec_output_order=[C.FROZEN_COREML_DEPTH_KEY, C.FROZEN_COREML_CONFIDENCE_KEY],
        semantic_evidence_sha256=C.FROZEN_COREML_OUTPUT_EVIDENCE_SHA256,
    )


def test_frozen_output_contract_handles_depth_and_confidence_both_in_unit_interval() -> None:
    contract = _frozen_output_contract()
    # This reproduces full115 ref091: numeric range cannot distinguish the heads.
    depth = np.full((1, 512, 896), 0.39923467, np.float32)
    confidence = np.full((1, 512, 896), 0.9748317, np.float32)
    for outputs in (
        {C.FROZEN_COREML_CONFIDENCE_KEY: confidence, C.FROZEN_COREML_DEPTH_KEY: depth},
        {C.FROZEN_COREML_DEPTH_KEY: depth, C.FROZEN_COREML_CONFIDENCE_KEY: confidence},
    ):
        got_depth, got_confidence, validation = C.extract_frozen_coreml_outputs(
            outputs, contract
        )
        np.testing.assert_array_equal(got_depth, depth[0])
        np.testing.assert_array_equal(got_confidence, confidence[0])
        assert validation["mapping_was_value_inferred"] is False
        assert validation["depth_key"] == C.FROZEN_COREML_DEPTH_KEY
        assert validation["confidence_key"] == C.FROZEN_COREML_CONFIDENCE_KEY


def test_frozen_output_contract_rejects_swapped_spec_rank() -> None:
    with pytest.raises(C.ContractError, match="spec output order"):
        C.resolve_frozen_coreml_output_contract(
            model_tree_sha256=C.FROZEN_COREML_MODEL_TREE_SHA256,
            spec_output_order=[C.FROZEN_COREML_CONFIDENCE_KEY, C.FROZEN_COREML_DEPTH_KEY],
            semantic_evidence_sha256=C.FROZEN_COREML_OUTPUT_EVIDENCE_SHA256,
        )


def test_frozen_output_validation_rejects_swapped_result_values() -> None:
    contract = _frozen_output_contract()
    depth = np.full((1, 512, 896), 2.25, np.float32)
    confidence = np.full((1, 512, 896), 0.73, np.float32)
    swapped = {
        C.FROZEN_COREML_DEPTH_KEY: confidence,
        C.FROZEN_COREML_CONFIDENCE_KEY: depth,
    }
    with pytest.raises(C.ContractError, match="confidence"):
        C.extract_frozen_coreml_outputs(swapped, contract)


def test_consistency_mask_outputs_camera_z_average() -> None:
    H, W = 12, 16
    names = [f"f{i}" for i in range(5)]
    depth = np.full((5, H, W), 2.0, np.float32)
    conf = np.full_like(depth, 0.9)
    K = np.repeat(np.array([[[20.0, 0.0, 7.5], [0.0, 20.0, 5.5], [0.0, 0.0, 1.0]]]), 5, axis=0)
    w2c = np.repeat(np.eye(4)[None], 5, axis=0)
    centers = np.zeros((5, 3), dtype=np.float64)
    # Tiny translation retains reprojection agreement on the fronto-parallel plane.
    for i in range(1, 5):
        centers[i, 0] = 0.04 + i * 0.005
        w2c[i] = _w2c(centers[i])
    dranges = np.repeat(np.array([[0.5, 4.0]], np.float32), 5, axis=0)
    got, stats = C.mask_all_depths(names, depth, conf, K, w2c, centers, dranges, neighbors=4)
    assert got.dtype == np.float32
    assert got.shape == depth.shape
    # Border normals are intentionally invalid; interior must remain and preserve camera-Z.
    assert np.count_nonzero(got[0]) > 0
    np.testing.assert_allclose(got[0][got[0] > 0], 2.0, atol=1e-5)
    assert stats[0]["geometric_support_required"] == 3


def test_limit_cache_is_unpublishable_and_signature_is_distinct() -> None:
    assert C.run_mode(1, 115) == "smoke_only"
    assert C.run_mode(None, 115) == "full_common_cache"
    assert "SMOKE_ONLY_LIMIT_1" in C.cache_signature(1, 115)
    assert "SMOKE" not in C.cache_signature(None, 115)


def test_frozen_split_is_exactly_93_reconstruction_and_22_heldout() -> None:
    reconstruction, heldout = C.frozen_split(115)
    assert heldout == list(range(4, 110, 5))
    assert len(reconstruction) == 93
    assert len(heldout) == 22
    assert set(reconstruction).isdisjoint(heldout)
    assert sorted(reconstruction + heldout) == list(range(115))


def test_output_directory_must_not_exist(tmp_path: Path) -> None:
    out = tmp_path / "fresh"
    C.create_exclusive_output_dir(out)
    assert out.is_dir()
    with pytest.raises(C.ContractError, match="already exists"):
        C.create_exclusive_output_dir(out)


def test_rgb_decode_uses_inter_area_ignores_exif_orientation_and_expected_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "x.jpg"
    bgr = np.zeros((32, 64, 3), np.uint8)
    bgr[..., 2] = 255
    called = {}

    def fake_imread(value: str, flags: int) -> np.ndarray:
        called["path"] = value
        called["flags"] = flags
        return bgr.copy()

    monkeypatch.setattr(cv2, "imread", fake_imread)
    rgb = C.decode_rgb(path, target_wh=(16, 8), expected_raw_wh=(64, 32))
    assert rgb.shape == (8, 16, 3)
    assert rgb.dtype == np.float32
    assert called["flags"] & cv2.IMREAD_IGNORE_ORIENTATION
    assert float(rgb[..., 0].mean()) > 0.95
    assert float(rgb[..., 2].mean()) < 0.05


def test_common_provenance_carries_parent_contract_fields() -> None:
    prov = C.common_provenance_skeleton(
        dataset_id="cap50",
        names=["a.jpg", "b.jpg"],
        reconstruction_names=["a.jpg"],
        heldout_names=["b.jpg"],
        metres_per_model_unit=1.0078,
        images_by_name={
            "a.jpg": {"sha256": "a" * 64, "size_bytes": 1},
            "b.jpg": {"sha256": "b" * 64, "size_bytes": 2},
        },
    )
    assert prov["schema_version"] == "b0-cap50-common-cache-provenance-v1"
    assert prov["coordinate_frame"] == "optimized_sfm_cv"
    assert prov["metres_per_model_unit"] == pytest.approx(1.0078)
    assert prov["dmcache"]["depth"] == {"shape": [2, 512, 896], "dtype": "float32"}
    assert prov["transductive_policy"]["present"] is True
    assert prov["transductive_policy"]["route_allowed"] is True
    assert prov["transductive_policy"]["quality_scoring_forbidden"] is False
    assert "139-frame optimized SfM" in prov["transductive_policy"]["reason"]
    split = prov["splits"][C.SPLIT_ID]
    assert split["reconstruction"]["frames"] == ["a.jpg"]
    assert split["heldout"]["frames"] == ["b.jpg"]
    json.dumps(prov, sort_keys=True)


def test_final_input_contract_binds_actual_files_and_reloads_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = ["a_tap-1.jpg", "b_tap-2.jpg"]
    reconstruction_path = tmp_path / "reconstruction.txt"
    heldout_path = tmp_path / "heldout.txt"
    reconstruction_path.write_text(f"{names[0]}\n", encoding="utf-8")
    heldout_path.write_text(f"{names[1]}\n", encoding="utf-8")
    dmcache_path = tmp_path / "dmcache.npz"
    model_cache_path = tmp_path / "model_cache.npz"
    dmcache_path.write_bytes(b"frozen dmcache")
    model_cache_path.write_bytes(b"frozen model cache")
    image_root = tmp_path / "images"
    image_root.mkdir()
    images = {
        names[0]: {"sha256": "a" * 64, "size_bytes": 11},
        names[1]: {"sha256": "b" * 64, "size_bytes": 12},
    }
    data = {
        "names": names,
        "reconstruction_names": [names[0]],
        "heldout_names": [names[1]],
        "metres_per_model_unit": 1.007804831494465,
        "images_by_name": images,
        "identity": {"image_root": {"path": str(image_root.resolve())}},
        "validation": {"jpeg_raw_dimensions_ignore_exif": [3840, 2160]},
        "split_files": {
            "reconstruction": {
                "path": str(reconstruction_path),
                "sha256": C.sha256_file(reconstruction_path),
            },
            "heldout": {"path": str(heldout_path), "sha256": C.sha256_file(heldout_path)},
        },
    }
    _patch_frozen_cohort_to_fixture(
        monkeypatch, names, data["reconstruction_names"], data["heldout_names"]
    )
    payload = C.build_final_input_contract(
        data,
        dataset_id="cap50-real-115",
        dmcache_path=dmcache_path,
        model_cache_path=model_cache_path,
        signature="frozen-signature",
        depth_shape=(2, 512, 896),
    )
    assert payload["schema_version"] == "b0-input-contract-v1"
    assert payload["dmcache"]["sha256"] == C.sha256_file(dmcache_path)
    assert payload["model_cache"]["sha256"] == C.sha256_file(model_cache_path)
    assert payload["images"]["root"] == str(image_root.resolve())
    assert payload["images"]["raw_size_wh"] == [3840, 2160]
    target = tmp_path / "input_contract.json"
    contract_hash = C.write_and_reload_final_input_contract(target, payload)
    assert contract_hash == C.sha256_file(target)
    with pytest.raises(C.ContractError, match="already exists"):
        C.write_and_reload_final_input_contract(target, payload)


def _formal_full_like_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, object], Path]:
    # Keep the formal 115/93/22 identity while shrinking only fixture HxW.
    monkeypatch.setattr(C, "PROC_H", 2)
    monkeypatch.setattr(C, "PROC_W", 3)
    names = [f"device_A_{index:03d}_tap-{1000 + index}.jpg" for index in range(115)]
    reconstruction_indices, heldout_indices = C.frozen_split(115)
    reconstruction = [names[index] for index in reconstruction_indices]
    heldout = [names[index] for index in heldout_indices]
    _patch_frozen_cohort_to_fixture(monkeypatch, names, reconstruction, heldout)
    monkeypatch.setattr(
        P, "FORMAL_UNIVERSE_FRAME_ORDER_SHA256", C.ordered_names_sha256(names)
    )
    monkeypatch.setattr(
        P,
        "FORMAL_RECONSTRUCTION_LIST_SHA256",
        C.ordered_names_sha256(reconstruction),
    )
    monkeypatch.setattr(
        P, "FORMAL_HELDOUT_LIST_SHA256", C.ordered_names_sha256(heldout)
    )

    image_root = tmp_path / "images"
    image_root.mkdir()
    images: dict[str, dict[str, object]] = {}
    for index, name in enumerate(names):
        image = image_root / name
        pixels = np.full((4, 6, 3), index % 255, dtype=np.uint8)
        encoded, jpeg = cv2.imencode(".jpg", pixels)
        assert encoded
        image.write_bytes(jpeg.tobytes())
        images[name] = {
            "sha256": C.sha256_file(image),
            "size_bytes": image.stat().st_size,
        }

    reconstruction_path = tmp_path / "reconstruction.txt"
    heldout_path = tmp_path / "heldout.txt"
    reconstruction_path.write_text("".join(f"{name}\n" for name in reconstruction), encoding="utf-8")
    heldout_path.write_text("".join(f"{name}\n" for name in heldout), encoding="utf-8")

    dmcache = tmp_path / "dmcache.npz"
    np.savez_compressed(
        dmcache,
        frames=np.asarray(names),
        dm=np.ones((115, 2, 3), dtype=np.float32),
        sig=np.asarray("cap50-common-camera-z-v1"),
        metres_per_model_unit=np.asarray(1.007804831494465, dtype=np.float64),
    )
    model_cache = tmp_path / "model_cache.npz"
    np.savez_compressed(
        model_cache,
        names=np.asarray(names),
        K=np.repeat(np.eye(3, dtype=np.float32)[None], 115, axis=0),
        w2c=np.repeat(np.eye(4, dtype=np.float32)[None], 115, axis=0),
        metres_per_model_unit=np.asarray(1.007804831494465, dtype=np.float64),
    )
    data = {
        "names": names,
        "reconstruction_names": reconstruction,
        "heldout_names": heldout,
        "metres_per_model_unit": 1.007804831494465,
        "images_by_name": images,
        "identity": {"image_root": {"path": str(image_root.resolve())}},
        "validation": {"jpeg_raw_dimensions_ignore_exif": [3840, 2160]},
        "split_files": {
            "reconstruction": {
                "path": str(reconstruction_path),
                "sha256": C.sha256_file(reconstruction_path),
            },
            "heldout": {
                "path": str(heldout_path),
                "sha256": C.sha256_file(heldout_path),
            },
        },
    }
    payload = C.build_final_input_contract(
        data,
        dataset_id="cap50-real-115",
        dmcache_path=dmcache,
        model_cache_path=model_cache,
        signature="cap50-common-camera-z-v1",
        depth_shape=(115, 2, 3),
    )
    contract = tmp_path / "input_contract.json"
    C.write_and_reload_final_input_contract(contract, payload)
    return contract, payload, image_root


def test_generated_full_like_contract_passes_formal_generic_preregister_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract, payload, image_root = _formal_full_like_contract(tmp_path, monkeypatch)
    bundle = P._load_generic_input_bundle(
        input_contract_path=contract, split_id=C.SPLIT_ID
    )
    assert bundle.image_root == image_root.resolve()
    assert bundle.universe == payload["dmcache"]["frame_order"]
    assert len(bundle.reconstruction) == 93
    assert len(bundle.heldout) == 22


@pytest.mark.parametrize("mutation", ["missing", "wrong"])
def test_formal_generic_preregister_rejects_missing_or_wrong_image_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _, payload, _ = _formal_full_like_contract(tmp_path, monkeypatch)
    mutated = copy.deepcopy(payload)
    if mutation == "missing":
        mutated["images"].pop("root")
    else:
        wrong = tmp_path / "wrong_images"
        wrong.mkdir()
        mutated["images"]["root"] = str(wrong.resolve())
    contract = tmp_path / f"input_contract_{mutation}.json"
    contract.write_text(json.dumps(mutated) + "\n", encoding="utf-8")
    with pytest.raises(P.PreRegistrationError, match=P.ROUTE_INPUT_NOT_EQUIVALENT):
        P._load_generic_input_bundle(input_contract_path=contract, split_id=C.SPLIT_ID)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "raw_size_wh"),
        ("wrong", "raw encoded image dimensions mismatch"),
    ],
)
def test_generated_contract_raw_dimensions_fail_closed_in_generic_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    message: str,
) -> None:
    _, payload, image_root = _formal_full_like_contract(tmp_path, monkeypatch)
    mutated = copy.deepcopy(payload)
    if mutation == "missing":
        mutated["images"].pop("raw_size_wh")
    else:
        # The fixture JPEG raster is 6x4.  A syntactically valid but false
        # contract dimension must be checked before any resize or evaluation.
        mutated["images"]["raw_size_wh"] = [7, 4]
    contract = tmp_path / f"input_contract_raw_size_{mutation}.json"
    contract.write_text(json.dumps(mutated) + "\n", encoding="utf-8")
    split = payload["splits"][C.SPLIT_ID]
    output = tmp_path / f"prepared_{mutation}.npz"

    with pytest.raises(E.PreparationError, match=message):
        E.prepare_evaluation_inputs(
            dmcache=Path(payload["dmcache"]["path"]),
            model_cache=Path(payload["model_cache"]["path"]),
            reconstruction_list=Path(split["reconstruction"]["path"]),
            heldout_list=Path(split["heldout"]["path"]),
            image_root=image_root,
            input_contract=contract,
            split_id=C.SPLIT_ID,
            out=output,
        )

    assert not output.exists()
    assert not E.provenance_path(output).exists()
