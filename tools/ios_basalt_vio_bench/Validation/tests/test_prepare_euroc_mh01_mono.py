import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prepare_euroc_mh01_mono.py"
SPEC = importlib.util.spec_from_file_location("prepare_euroc_mh01_mono", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class EuRoCManifestBuilderTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        contents = {
            "mav0/cam0/data.csv": "#timestamp,filename\n0,0.png\n100,100.png\n",
            "mav0/cam0/sensor.yaml": "sensor_type: camera\n",
            "mav0/cam0/data/0.png": "left0",
            "mav0/cam0/data/100.png": "left1",
            "mav0/imu0/data.csv": "#timestamp,w_x,w_y,w_z,a_x,a_y,a_z\n0,0,0,0,0,0,9.81\n",
            "mav0/imu0/sensor.yaml": "sensor_type: imu\n",
            "mav0/state_groundtruth_estimate0/data.csv": "#timestamp,p,q\n0,0\n",
        }
        for relative, data in contents.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
        return temporary, root

    def test_builds_sorted_cam0_only_content_addressed_manifest(self):
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        first = MODULE.build_manifest(root)
        second = MODULE.build_manifest(root)
        self.assertEqual(first, second)
        self.assertEqual(first["dataset_name"], "EuRoC_MH_01_easy")
        self.assertEqual(first["input_camera_count"], 1)
        paths = [record["relative_path"] for record in first["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertNotIn("mav0/cam1/data.csv", paths)
        self.assertEqual(len(first["dataset_sha256"]), 64)

    def test_rejects_unindexed_or_missing_camera_images(self):
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        (root / "mav0/cam0/data/unindexed.png").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "image/index mismatch"):
            MODULE.build_manifest(root)

    def test_writes_manifest_atomically(self):
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        output = root / "input_manifest.json"
        MODULE.write_manifest(root, output)
        document = json.loads(output.read_text())
        self.assertEqual(document["schema_version"], 1)
        self.assertFalse(list(root.glob(".input_manifest.json.*")))

    def test_identity_matches_the_swift_loader_golden_vector(self):
        records = [
            MODULE.FileRecord("camera0_index", "mav0/cam0/data.csv", 3, "a" * 64),
            MODULE.FileRecord("camera_image", "mav0/cam0/data/0.png", 2, "b" * 64),
            MODULE.FileRecord("imu_index", "mav0/imu0/data.csv", 4, "c" * 64),
        ]
        self.assertEqual(
            MODULE.dataset_identity(records),
            "e2d4121a08633d4c3a04b8df01e50a330d3d41ce55085d48787932e9177d54cc",
        )


if __name__ == "__main__":
    unittest.main()
