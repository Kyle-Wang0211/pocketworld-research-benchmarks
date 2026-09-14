import site, os, pathlib
sp = site.getsitepackages()[0]
d = pathlib.Path(sp) / "pytorch3d" / "implicitron" / "dataset"
d.mkdir(parents=True, exist_ok=True)
(pathlib.Path(sp) / "pytorch3d" / "implicitron" / "__init__.py").write_text("")
(d / "__init__.py").write_text("")
(d / "types.py").write_text(
    '"""Stub: MVSAnywhere imports these only to define DynamicReplicaDataset, a training\n'
    'dataset unused at inference. FrameAnnotation must be a real dataclass because it is\n'
    'subclassed with @dataclass."""\n'
    "from dataclasses import dataclass, field\n"
    "from typing import Any, Optional\n\n"
    "@dataclass\n"
    "class FrameAnnotation:\n"
    "    sequence_name: str = \"\"\n"
    "    frame_number: int = 0\n"
    "    frame_timestamp: float = 0.0\n"
    "    image: Optional[Any] = None\n"
    "    depth: Optional[Any] = None\n"
    "    mask: Optional[Any] = None\n"
    "    viewpoint: Optional[Any] = None\n"
    "    meta: Optional[Any] = None\n\n"
    "def load_dataclass(*a, **k):\n"
    "    raise RuntimeError('pytorch3d stub: DynamicReplicaDataset is not used in this run.')\n"
)
print("wrote", d / "types.py")
