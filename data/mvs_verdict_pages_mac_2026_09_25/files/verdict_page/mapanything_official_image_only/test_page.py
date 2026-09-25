#!/usr/bin/env python3
import json
import unittest
from pathlib import Path


PAGE = Path(__file__).resolve().parent


class OfficialImageOnlyPageTests(unittest.TestCase):
    def test_page_identifies_the_unchanged_official_image_only_chain(self):
        html = (PAGE / "index.html").read_text()
        meta = json.loads((PAGE / "bin/meta.json").read_text())
        self.assertIn("100% 官方纯图片链", html)
        self.assertIn("未输入相机位姿或稀疏点", html)
        self.assertIn("官方 1% IQR 体素", html)
        self.assertEqual(meta["mapanything_official"]["n"], 864_738)

    def test_binary_sizes_match_the_official_ply(self):
        meta = json.loads((PAGE / "bin/meta.json").read_text())
        count = meta["mapanything_official"]["n"]
        self.assertEqual((PAGE / "bin/mapanything_official.pos").stat().st_size, count * 12)
        self.assertEqual((PAGE / "bin/mapanything_official.col").stat().st_size, count * 3)


if __name__ == "__main__":
    unittest.main()
