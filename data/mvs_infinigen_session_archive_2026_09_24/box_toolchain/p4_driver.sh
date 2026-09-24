#!/bin/bash
# All weakly-supported-surface ablation arms, sequential.
# Single variable per arm; every other flag verbatim from baseline arm A (arms.sh lines 13-32).
set -u
export PW_AV_BIN=/root/av32_build/Linux-x86_64
export PW_AV_ROOT=""
export PW_AV_LIB=/root/av32_build/Linux-x86_64:/root/av32_prefix/lib
W=/root/p4
run(){ local N=$1; shift; env "$@" /root/p4_arm.sh $N; }

run A0                                     # control: no override -> upstream defaults
run NEG  AV_K_REL=0.1 AV_K_ABS=10000 AV_K_OUTL=100 AV_NSIGMA_JUMP=4 AV_NSIGMA_FRONT=2 AV_NSIGMA_BACK=2
run P4   AV_K_ABS=1000 AV_K_OUTL=400 AV_NSIGMA_JUMP=3 AV_NSIGMA_FRONT=4 AV_NSIGMA_BACK=4
run P1   AV_K_ABS=1000
run P2   AV_K_OUTL=400
run P3   AV_NSIGMA_JUMP=3 AV_NSIGMA_FRONT=4 AV_NSIGMA_BACK=4
run P4b  AV_K_ABS=1000 AV_K_OUTL=400 AV_NSIGMA_JUMP=3 AV_NSIGMA_BACK=4
run P3b  AV_NSIGMA_JUMP=3 AV_NSIGMA_BACK=4
echo "ALL-ARMS-COMPLETE"
