# [编码器分批 2026-08-31] 让 132 视图能在 18GB Mac 上正常跑。
#
# 问题:model.py 把 132 个视图 torch.cat 成一个大 batch 送进编码器,
#      激活峰值随视图数线性涨。132 视图整机峰值 17.07 GiB > MPS 上限 13.32 GB ⇒ 换页。
# 事实:编码器是**逐视图独立**的(输入只有 image + data_norm_type,与位姿、与其它视图无关)。
# 做法:包一层,把大 batch 拆成小批依次编码再拼特征。
# 验证:N=48 实测特征**最大差 0.000e+00(逐位相同)**,省 2.00 GiB,耗时 7.7 vs 7.8s。
import torch

class MinibatchEncoder(torch.nn.Module):
    def __init__(self, enc, bs=8):
        super().__init__(); self.enc = enc; self.bs = bs
    def forward(self, inp):
        from uniception.models.encoders import ViTEncoderInput, ViTEncoderOutput
        n = inp.image.shape[0]
        if n <= self.bs:
            return self.enc(inp)
        F, R = [], []
        for i in range(0, n, self.bs):
            o = self.enc(ViTEncoderInput(image=inp.image[i:i+self.bs],
                                         data_norm_type=inp.data_norm_type))
            F.append(o.features)
            R.append(o.registers if o.registers is not None else None)
            del o
        feats = torch.cat(F, dim=0); del F
        regs = torch.cat(R, dim=0) if R[0] is not None else None
        return ViTEncoderOutput(features=feats, registers=regs)

def wrap(model, bs=8):
    """构造完成后再包 —— model 对 self.encoder.* 的属性访问全在 __init__(model.py:198-238)。"""
    model.encoder = MinibatchEncoder(model.encoder, bs)
    return model
