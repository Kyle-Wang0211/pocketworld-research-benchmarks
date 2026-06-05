import sys
import types
import importlib.machinery

triton_alignment = types.ModuleType('loop_utils.alignment_triton')
triton_alignment.__spec__ = importlib.machinery.ModuleSpec('loop_utils.alignment_triton', loader=None)

def robust_weighted_estimate_sim3_triton(*args, **kwargs):
    raise RuntimeError('Triton alignment stub called unexpectedly during npz_output_process point-cloud export')

triton_alignment.robust_weighted_estimate_sim3_triton = robust_weighted_estimate_sim3_triton
sys.modules['loop_utils.alignment_triton'] = triton_alignment

numba = types.ModuleType('numba')
numba.__spec__ = importlib.machinery.ModuleSpec('numba', loader=None)

def njit(*args, **kwargs):
    if args and callable(args[0]) and len(args) == 1 and not kwargs:
        return args[0]
    def decorator(fn):
        return fn
    return decorator

numba.njit = njit
sys.modules['numba'] = numba

sklearn = types.ModuleType('sklearn')
linear_model = types.ModuleType('sklearn.linear_model')
sklearn.__spec__ = importlib.machinery.ModuleSpec('sklearn', loader=None)
linear_model.__spec__ = importlib.machinery.ModuleSpec('sklearn.linear_model', loader=None)

class _UnusedSklearnEstimator:
    def __init__(self, *args, **kwargs):
        raise RuntimeError('sklearn estimator stub called unexpectedly during npz_output_process point-cloud export')

linear_model.LinearRegression = _UnusedSklearnEstimator
linear_model.RANSACRegressor = _UnusedSklearnEstimator
sklearn.linear_model = linear_model
sys.modules['sklearn'] = sklearn
sys.modules['sklearn.linear_model'] = linear_model

loop_detector = types.ModuleType('loop_utils.loop_detector')
loop_detector.__spec__ = importlib.machinery.ModuleSpec('loop_utils.loop_detector', loader=None)

class LoopDetector:
    def __init__(self, *args, **kwargs):
        raise RuntimeError('LoopDetector stub called unexpectedly during npz_output_process point-cloud export')

loop_detector.LoopDetector = LoopDetector
sys.modules['loop_utils.loop_detector'] = loop_detector

depth_anything_3 = types.ModuleType('depth_anything_3')
depth_anything_3.__spec__ = importlib.machinery.ModuleSpec('depth_anything_3', loader=None)
depth_anything_3.__path__ = []
depth_anything_3_api = types.ModuleType('depth_anything_3.api')
depth_anything_3_api.__spec__ = importlib.machinery.ModuleSpec('depth_anything_3.api', loader=None)

class DepthAnything3:
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        raise RuntimeError('DepthAnything3 stub called unexpectedly during npz_output_process point-cloud export')

depth_anything_3_api.DepthAnything3 = DepthAnything3
depth_anything_3.api = depth_anything_3_api
sys.modules['depth_anything_3'] = depth_anything_3
sys.modules['depth_anything_3.api'] = depth_anything_3_api
