#!/bin/bash
# pytorch3d is imported at module load only by datasets/dynamic_replica.py (a training dataset we
# never touch). Building pytorch3d against torch 2.11 is a long compile for an unused import, so we
# stub the one symbol it needs. If anything actually calls it, it raises loudly rather than silently
# returning wrong numbers.
SP=$(/root/venv_mvsa/bin/python -c "import site;print(site.getsitepackages()[0])")
mkdir -p "$SP/pytorch3d/renderer"
cat > "$SP/pytorch3d/__init__.py" <<'PY'
__version__ = "0.0.0-stub-for-mvsanywhere-unused-import"
PY
cat > "$SP/pytorch3d/renderer/__init__.py" <<'PY'
from .cameras import PerspectiveCameras  # noqa: F401
PY
cat > "$SP/pytorch3d/renderer/cameras.py" <<'PY'
class PerspectiveCameras:  # stub: only needed so datasets/dynamic_replica.py can be imported
    def __init__(self, *a, **k):
        raise RuntimeError(
            "pytorch3d stub: DynamicReplicaDataset is not used in this run. "
            "If you see this, real pytorch3d is required."
        )
PY
/root/venv_mvsa/bin/python -c "from pytorch3d.renderer.cameras import PerspectiveCameras; print('P3D_STUB_OK')"
