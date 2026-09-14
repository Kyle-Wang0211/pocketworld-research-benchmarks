import ast, os
p = "/root/mvsanywhere/src/mvsanywhere/modules/vit_modules.py"
s = open(p).read()
assert "_NO_MONO" not in s, "已打过补丁"

hdr = '''import os
# ---------------------------------------------------------------------------------------------
# 单目分支旁路开关(MVSA_NO_MONO=1)。做法照抄同一实验室 SimpleRecon 的消融口径:
#   "we ablate the cost volume entirely by zeroing its output (creating a monocular method)"
#   -- SimpleRecon, arXiv 2208.14743, Sec.4 Ablations
# 这里方向相反: 把 *单目* 支路的输出置零, 留下纯 cost volume。
# 单目特征只经 CostVolumeViTEncoder 进入模型(sr_depth_model.py 里 cur_feats 被它的输出整个替换),
# 所以堵住它内部这两条路径就是完全旁路:
#   (1) CostVolumePatchEmbed: img_feat 被 torch.cat 进 cost volume -> 置零(保留通道结构)
#   (2) ViT 每层的加性融合 x = x + cv_feat_fusers(...)             -> 跳过
_NO_MONO = os.environ.get("MVSA_NO_MONO", "0") == "1"
_FIRED = {"embed": 0, "fuse": 0, "printed": 0}
'''
s = hdr + s

old1 = """                img_feat = self.resize_layers[i](img_feat)
                x = torch.cat([x, img_feat], dim=1)"""
new1 = """                img_feat = self.resize_layers[i](img_feat)
                if _NO_MONO:
                    img_feat = torch.zeros_like(img_feat)
                    _FIRED["embed"] += 1
                x = torch.cat([x, img_feat], dim=1)"""
assert old1 in s, "anchor 1 missing"
s = s.replace(old1, new1)

old2 = """            # Fuse with mono branch ViT layer
            if i in self.feat_fuser_layers_idx:"""
new2 = """            # Fuse with mono branch ViT layer
            if _NO_MONO and i in self.feat_fuser_layers_idx:
                _FIRED["fuse"] += 1
            if (not _NO_MONO) and i in self.feat_fuser_layers_idx:"""
assert old2 in s, "anchor 2 missing"
s = s.replace(old2, new2)

# 自证: 前 3 次前向打印命中计数, 证明开关真的生效(不是静默空转)
old3 = """            if i in self.intermediate_layers_idx:
                feats.append((x[:, 1:], x[:, 0]))
                
        return feats"""
new3 = """            if i in self.intermediate_layers_idx:
                feats.append((x[:, 1:], x[:, 0]))

        if _NO_MONO and _FIRED["printed"] < 3:
            _FIRED["printed"] += 1
            print("[MVSA_NO_MONO] bypass active: patch-embed zeroed x{}, ViT fusion skipped x{}".format(
                _FIRED["embed"], _FIRED["fuse"]), flush=True)
        return feats"""
assert old3 in s, "anchor 3 missing"
s = s.replace(old3, new3)

ast.parse(s)
open(p, "w").write(s)
print("PATCHED ok, _NO_MONO 出现", s.count("_NO_MONO"), "次")
