#!/bin/bash
# Bootstrap the bundled conversion engine.
#
# Downloads a relocatable CPython (python-build-standalone) into engine/python and
# installs OpenUSD (usd-core) + numpy + Pillow into it. Run once after cloning.
# The result (engine/python) is gitignored — it's a build artifact, not source.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PYVER="3.14.6"
PBS_TAG="20260623"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PYVER}%2B${PBS_TAG}-aarch64-apple-darwin-install_only.tar.gz"
TARBALL="$HERE/vendor-cpython-${PYVER}-arm64.tar.gz"
PY="$HERE/python/bin/python3.14"

if [ ! -x "$PY" ]; then
  if [ ! -f "$TARBALL" ]; then
    echo "==> Downloading relocatable CPython ${PYVER} (arm64)"
    curl -fL "$URL" -o "$TARBALL"
  fi
  echo "==> Extracting interpreter"
  tar -xzf "$TARBALL" -C "$HERE"
fi

echo "==> Installing OpenUSD (usd-core) + numpy + Pillow"
"$PY" -m pip install --isolated --no-warn-script-location usd-core numpy Pillow

echo "==> Verifying"
"$PY" -c "from pxr import Usd, UsdSkel; print('OpenUSD', Usd.GetVersion())"
echo "Engine ready: $HERE/python"
