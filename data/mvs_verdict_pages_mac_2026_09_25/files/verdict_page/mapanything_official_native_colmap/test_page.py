#!/usr/bin/env python3
import json
import unittest
from pathlib import Path


PAGE = Path(__file__).resolve().parent


class OfficialNativeColmapPageTests(unittest.TestCase):
    def test_page_identifies_the_native_colmap_chain(self):
        html = (PAGE / "index.html").read_text()
        meta = json.loads((PAGE / "bin/meta.json").read_text())
        self.assertIn("原始 COLMAP 直通官方链", html)
        self.assertIn("不经过 MVS→COLMAP 转换器", html)
        self.assertIn("官方 1% IQR 体素", html)
        self.assertEqual(meta["mapanything_native_colmap"]["n"], 1_405_572)

    def test_binary_sizes_match_the_official_ply(self):
        meta = json.loads((PAGE / "bin/meta.json").read_text())
        count = meta["mapanything_native_colmap"]["n"]
        self.assertEqual(
            (PAGE / "bin/mapanything_native_colmap.pos").stat().st_size,
            count * 12,
        )
        self.assertEqual(
            (PAGE / "bin/mapanything_native_colmap.col").stat().st_size,
            count * 3,
        )


if __name__ == "__main__":
    unittest.main()
