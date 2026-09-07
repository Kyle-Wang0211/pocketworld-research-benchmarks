"""Fuse MonoMVSNet depths with the OFFICIAL CasDiffMVS filter.py::filter_depth (same gate as the casdiff pane:
geo >=3 views, 1px, 1%, depth averaged). Only difference: photo threshold = MonoMVSNet single confidence > 0.55
(its official DTU value), applied to all three stage slots because MonoMVSNet emits one confidence map."""
import sys, os
sys.path.insert(0, "/root/diffmvs")
from filter import filter_depth
filter_depth("/root/mono_in/scan1", "/root/mono_fuse/scan1", "/root/mono_fuse/mono_official_gate.ply",
             3, 1.0, 0.01, [0.55, 0.55, 0.55], "casdiffmvs", "general")
