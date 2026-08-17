"""按需加载 LightGlue 的单个子模块,绕开 lightglue/__init__.py。

为什么必须绕:__init__.py 会 import .sift,而 sift.py `import pycolmap`,
pycolmap 自带第二份 libomp,与 torch 的 libomp 冲突 → OMP Error #15 直接 abort。
官方绕法 KMP_DUPLICATE_LIB_OK 自带"可能静默产生错误结果"警告,质量臂不可接受。

⚠️ 由此产生一条硬边界:torch(匹配/提取)与 pycolmap(几何验证/建图)不能同进程,
   必须分两段跑,中间用 DB 传递。
"""
import importlib.util
import sys
import types
from pathlib import Path

import kornia_stub  # noqa: F401  —— 必须先于任何 lightglue 子模块

_PKG_DIR = Path(__file__).resolve().parent / "LightGlue" / "lightglue"
_ALIAS = "lgx"


def _ensure_pkg():
    if _ALIAS not in sys.modules:
        p = types.ModuleType(_ALIAS)
        p.__path__ = [str(_PKG_DIR)]
        sys.modules[_ALIAS] = p


def load(name: str):
    """load('aliked') → 模块对象。子模块内的 `from .utils import ...` 会解析到 lgx.utils。"""
    _ensure_pkg()
    full = f"{_ALIAS}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, _PKG_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod
