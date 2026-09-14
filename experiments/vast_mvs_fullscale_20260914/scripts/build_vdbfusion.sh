#!/bin/bash
set -x
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq libopenvdb-dev libtbb-dev libblosc-dev libeigen3-dev libboost-iostreams-dev cmake build-essential
cd /root && rm -rf vdbfusion_src && git clone --depth 1 https://github.com/PRBonn/vdbfusion.git vdbfusion_src
cd /root/vdbfusion_src
head -3 LICENSE
/venv/main/bin/pip install -v . 2>&1 | tail -30
/venv/main/bin/python -c "import vdbfusion,inspect;print(VDBFUSION_OK);print(inspect.signature(vdbfusion.VDBVolume.__init__));print([m for m in dir(vdbfusion.VDBVolume) if not m.startswith(_)])"
echo BUILD_DONE
