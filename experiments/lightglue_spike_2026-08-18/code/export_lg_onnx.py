"""把 LightGlue(aliked 权重)匹配器导出成 ONNX。

只导匹配器:实测它占单对耗时的 96.3%(27 次注意力 + 9 个前馈)。
剪枝必须关(depth/width_confidence=-1)—— 一是它改变输出违反无损,
二是它引入数据相关的控制流,ONNX 图里表达不了。
"""
import sys, torch
sys.path.insert(0, ".")
import lg_load
lgm = lg_load.load("lightglue")


class Wrap(torch.nn.Module):
    def __init__(self, lg):
        super().__init__(); self.lg = lg
    def forward(self, kpts0, desc0, size0, kpts1, desc1, size1):
        out = self.lg({"image0": {"keypoints": kpts0, "descriptors": desc0, "image_size": size0},
                       "image1": {"keypoints": kpts1, "descriptors": desc1, "image_size": size1}})
        return out["matches0"], out["matching_scores0"]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1024
    lg = lgm.LightGlue(features="aliked", depth_confidence=-1, width_confidence=-1).eval()
    m = Wrap(lg).eval()
    n1 = n + 137          # 两图点数必须不同,否则被追踪成同一个静态维度
    args = (torch.rand(1, n, 2) * 1000, torch.rand(1, n, 128),
            torch.tensor([[1600.0, 1200.0]]),
            torch.rand(1, n1, 2) * 1000, torch.rand(1, n1, 128),
            torch.tensor([[1600.0, 1200.0]]))
    D0 = torch.export.Dim("n0", min=64, max=32768)
    D1 = torch.export.Dim("n1", min=64, max=32768)
    dyn = ({1: D0}, {1: D0}, None, {1: D1}, {1: D1}, None)
    with torch.no_grad():
        torch.onnx.export(
            m, args, "lightglue_aliked.onnx",
            input_names=["kpts0", "desc0", "size0", "kpts1", "desc1", "size1"],
            output_names=["matches0", "mscores0"],
            dynamic_shapes=dyn, opset_version=18, dynamo=True)
    import os
    print(f"导出成功 lightglue_aliked.onnx  {os.path.getsize('lightglue_aliked.onnx')/1e6:.1f} MB")


if __name__ == "__main__":
    main()
