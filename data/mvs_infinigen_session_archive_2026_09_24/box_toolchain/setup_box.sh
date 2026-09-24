set -e
cd /root
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  libeigen3-dev libceres-dev libfreeimage-dev libgoogle-glog-dev libgflags-dev \
  libsqlite3-dev libflann-dev libmetis-dev liblz4-dev libcurl4-openssl-dev \
  libssl-dev libgmp-dev libmpfr-dev libsuitesparse-dev libgtest-dev \
  libboost-all-dev zlib1g-dev >/dev/null 2>&1 || apt-get install -y \
  libeigen3-dev libceres-dev libfreeimage-dev libgoogle-glog-dev libgflags-dev \
  libsqlite3-dev libflann-dev libmetis-dev liblz4-dev libcurl4-openssl-dev \
  libssl-dev libgmp-dev libmpfr-dev libsuitesparse-dev libgtest-dev zlib1g-dev
echo "APT_DONE"
rm -rf /root/cgal6 && mkdir -p /root/cgal6
cd /root/cgal6
curl -sSL -o CGAL.tar.xz https://github.com/CGAL/cgal/releases/download/v6.0.1/CGAL-6.0.1-library.tar.xz
tar xf CGAL.tar.xz
ls /root/cgal6
grep -rn "define CGAL_VERSION " /root/cgal6/CGAL-6.0.1/include/CGAL/version.h | head -3
grep -rn "define CGAL_VERSION_NR" /root/cgal6/CGAL-6.0.1/include/CGAL/version.h | head -3
echo "CGAL_DONE"
