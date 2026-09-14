import pathlib, re
p = pathlib.Path("/root/lf_probe/NeuralFusion/pipeline/translator.py")
s = p.read_text()
n = s.count(".view(")
# torch >= 1.8 refuses .view() on non-contiguous tensors produced by expand/permute.
# .reshape() is defined to fall back to a copy in exactly that case, so this is behaviour-preserving.
s2 = s.replace(".view(", ".reshape(")
p.write_text(s2)
print(f"translator.py: replaced {n} .view( with .reshape(")
