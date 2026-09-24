#!/usr/bin/env python3
"""Run official_pytorch_k_sweep with the oracle MPS query-chunked SDPA installed.

This is a launcher shim, not a new pipeline: it imports the proven
``install_mps_chunked_sdpa`` from ``da3base_official_streaming_oracle`` (the
exact function the K=35 oracle runs used), installs it on
``torch.nn.functional.scaled_dot_product_attention``, then delegates to the
unmodified ``official_pytorch_k_sweep.main()``. The chunked SDPA is a
runtime-scheduling change only (query-row blocking of the same matmuls and
softmax); it exists to stay under the MPS single-buffer allocation limit that
historically killed K=35 @ process_res 742 ("Invalid buffer size: 89.01 GiB").
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    argv = sys.argv[1:]
    query_chunk = 256
    min_gib = 2.0
    passthrough: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--sdpa-query-chunk":
            query_chunk = int(argv[i + 1])
            i += 2
        elif argv[i] == "--sdpa-min-gib":
            min_gib = float(argv[i + 1])
            i += 2
        else:
            passthrough.append(argv[i])
            i += 1

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import torch

    from da3base_official_streaming_oracle import install_mps_chunked_sdpa

    install_mps_chunked_sdpa(torch, query_chunk, min_gib)
    print(
        f"k_sweep_mps_chunked_sdpa installed query_chunk={query_chunk} min_gib={min_gib}",
        flush=True,
    )

    import official_pytorch_k_sweep as sweep

    sys.argv = ["official_pytorch_k_sweep.py", *passthrough]
    return sweep.main()


if __name__ == "__main__":
    raise SystemExit(main())
