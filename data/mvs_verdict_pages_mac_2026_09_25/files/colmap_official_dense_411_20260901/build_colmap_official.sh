#!/usr/bin/env bash
set -euo pipefail

cd /root/colmap-4.1.1-src
exec /usr/bin/ninja -C build -j4 colmap
