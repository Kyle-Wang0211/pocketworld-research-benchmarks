# 官方 README Example 1: Images + Camera Intrinsics(只喂内参,不喂位姿/尺度)。
import os,time,threading,resource,json,numpy as np,torch
from pathlib import Path
threading.Thread(target=lambda:[(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**30>13 and (print("🔴守卫",flush=True),os._exit(9)),time.sleep(0.3)) for _ in iter(int,1)],daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import preprocess_inputs
from minibatch_encoder import wrap
from PIL import Image
FR=Path.home()/".codex/builds/pw-dense-xorwow-2000-20260829/FrozenB28"
sel=json.loads((FR/"selection.json").read_text())["images"][:132]
raw=[{"img":np.asarray(Image.open(f"images_rgb/{im['name']}").convert("RGB"),np.uint8),
      "intrinsics":np.array(im["K"],np.float32).reshape(3,3)} for im in sel]
views=preprocess_inputs(raw,verbose=False)
m=wrap(MapAnything.from_pretrained("weights/v1").to("mps").eval(),8)
t=time.time()
with torch.inference_mode():
    outs=m.infer(views,memory_efficient_inference=True,minibatch_size=1,use_amp=True,
                 amp_dtype="bf16",apply_mask=True,mask_edges=True)
print(f"  内参模式 {time.time()-t:.0f}s",flush=True)
np.savez_compressed("dpk_intr.npz",
  D=np.stack([o["depth_z"][0].squeeze(-1).float().cpu().numpy() for o in outs]).astype(np.float16),
  M=np.stack([o["mask"][0].squeeze(-1).cpu().numpy().astype(bool) for o in outs]),
  K=np.stack([o["intrinsics"][0].float().cpu().numpy() for o in outs]),
  P=np.stack([o["camera_poses"][0].float().cpu().numpy() for o in outs]))
print("  ✅ dpk_intr.npz",flush=True)
