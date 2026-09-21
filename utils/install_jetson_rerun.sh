#!/usr/bin/env bash
# Installs rerun-sdk into the pixi env on the Jetson, outside pixi.lock.
#
# Why not a normal dependency: the Jetson target pins numpy <2 (JetPack's cv2 is built against apt
# numpy 1.26), and every rerun-sdk since 0.24 declares `numpy>=2` — on PyPI and conda-forge alike —
# which pixi can't override, so the solver rejects the pair. 0.38.1 actually runs fine on numpy 1.26
# (it ships a _numpy_compatibility shim; the requirement is metadata only). So the wheel goes in with
# --no-deps, and its real runtime deps (attrs, pillow, psutil, pyarrow, typing_extensions) are carried
# by [target.jetson.dependencies] in pixi.toml.
#
# Idempotent: exits at once if the pinned version is importable; `--force` reinstalls. Run it with
# `pixi run install-rerun` (Jetson only, see [target.jetson.tasks]); tasks that need rerun on the
# Jetson `depends-on` it, so they self-heal if a `pixi install` ever prunes the package.
set -euo pipefail

# Keep in sync with rerun-sdk in [target.osx-arm64.pypi-dependencies] (pixi.toml) so both platforms
# speak the same rerun wire format.
RERUN_VERSION="0.38.1"

PYTHON="$CONDA_PREFIX/bin/python"
force=""
[[ "${1:-}" == "--force" ]] && force="--reinstall"

if [[ -z "$force" ]] && "$PYTHON" - "$RERUN_VERSION" <<'PY'
import sys
try:
    import rerun
except ImportError:
    sys.exit(1)
sys.exit(0 if rerun.__version__ == sys.argv[1] else 1)
PY
then
    echo "rerun-sdk $RERUN_VERSION already installed in $CONDA_PREFIX"
    exit 0
fi

# uv is on PATH inside the env (a dora-rs-cli dependency); pip is not.
uv pip install --python "$PYTHON" --no-deps $force "rerun-sdk==$RERUN_VERSION"
"$PYTHON" -c "import rerun, numpy; print(f'rerun-sdk {rerun.__version__} installed (numpy {numpy.__version__})')"
