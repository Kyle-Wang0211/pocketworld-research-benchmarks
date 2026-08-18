#!/usr/bin/env bash
# GitHub gist 只能放文本,所以两个二进制附件以 base64 存放。还原:
base64 -d model.onnx.b64 > model.onnx
base64 -d input_small.npz.b64 > input_small.npz
python3 repro.py
