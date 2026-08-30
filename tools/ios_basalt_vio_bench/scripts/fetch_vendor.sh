#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BENCH_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)
VENDOR_ROOT="${BENCH_ROOT}/Vendor"
BASALT_ROOT="${VENDOR_ROOT}/basalt"
HEADERS_ROOT="${VENDOR_ROOT}/basalt-headers"

BASALT_URL=https://gitlab.com/VladyslavUsenko/basalt.git
BASALT_COMMIT=0f3b2b52c807f70ff4e2973ce253c73329eea7bc
HEADERS_URL=https://gitlab.com/VladyslavUsenko/basalt-headers.git
HEADERS_COMMIT=aa441ba3e51050c47ba1902537792a2e4db7e43d
REGISTRY_BASELINE=05442024c3fda64320bd25d2251cc9807b84fb6f

prepare_checkout() {
  url=$1
  commit=$2
  destination=$3

  if [ -e "$destination" ] && [ ! -d "${destination}/.git" ]; then
    printf 'refusing non-Git vendor path: %s\n' "$destination" >&2
    exit 1
  fi
  if [ ! -d "${destination}/.git" ]; then
    git clone --filter=blob:none --no-checkout "$url" "$destination"
  else
    actual_url=$(git -C "$destination" remote get-url origin)
    if [ "$actual_url" != "$url" ]; then
      printf 'vendor origin mismatch at %s\n' "$destination" >&2
      exit 1
    fi
    git -C "$destination" diff --quiet --ignore-submodules=none -- || {
      printf 'refusing dirty vendor checkout: %s\n' "$destination" >&2
      exit 1
    }
    git -C "$destination" diff --cached --quiet --ignore-submodules=none -- || {
      printf 'refusing staged vendor changes: %s\n' "$destination" >&2
      exit 1
    }
  fi

  git -C "$destination" fetch --filter=blob:none --depth 1 origin "$commit"
  git -C "$destination" checkout --detach "$commit"
}

mkdir -p "$VENDOR_ROOT"
prepare_checkout "$BASALT_URL" "$BASALT_COMMIT" "$BASALT_ROOT"
git -C "$BASALT_ROOT" submodule sync -- thirdparty/vcpkg
git -C "$BASALT_ROOT" submodule update --init --depth 1 thirdparty/vcpkg
git -C "${BASALT_ROOT}/thirdparty/vcpkg" fetch --depth 1 origin "$REGISTRY_BASELINE"
prepare_checkout "$HEADERS_URL" "$HEADERS_COMMIT" "$HEADERS_ROOT"

"${SCRIPT_DIR}/verify_vendor.sh"
