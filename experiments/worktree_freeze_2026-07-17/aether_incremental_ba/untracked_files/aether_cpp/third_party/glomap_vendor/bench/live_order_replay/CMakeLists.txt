cmake_minimum_required(VERSION 3.20)
project(aether_live_order_stored_match_replay LANGUAGES CXX)

# Independent host-only target.  It links an already-built glomap_core archive
# so adding this experiment cannot mutate the product/vendor target graph.
set(GLOMAP_CORE_ARCHIVE "" CACHE FILEPATH "Path to libglomap_core.a")
if(NOT EXISTS "${GLOMAP_CORE_ARCHIVE}")
  message(FATAL_ERROR "Pass -DGLOMAP_CORE_ARCHIVE=/absolute/path/libglomap_core.a")
endif()

get_filename_component(VENDOR_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
get_filename_component(AETHER_CPP_ROOT "${VENDOR_ROOT}/../.." ABSOLUTE)

add_library(aether_glomap_core STATIC IMPORTED GLOBAL)
set_target_properties(aether_glomap_core PROPERTIES
  IMPORTED_LOCATION "${GLOMAP_CORE_ARCHIVE}")

add_executable(live_order_stored_match_replay_exe
  "${VENDOR_ROOT}/bench/live_order_stored_match_replay.cc")
set_target_properties(live_order_stored_match_replay_exe PROPERTIES
  CXX_STANDARD 17 CXX_STANDARD_REQUIRED YES)
target_compile_definitions(live_order_stored_match_replay_exe PRIVATE
  EIGEN_MPL2_ONLY GLOG_USE_GLOG_EXPORT GLOG_NO_ABBREVIATED_SEVERITIES
  GLOG_VERSION_MAJOR=0 GLOG_VERSION_MINOR=7
  GLOMAP_CUDA_DISABLED COLMAP_CUDA_ENABLED=0)
target_include_directories(live_order_stored_match_replay_exe BEFORE PRIVATE
  "${VENDOR_ROOT}/colmap-src"
  "${VENDOR_ROOT}/glomap-src"
  "${VENDOR_ROOT}/poselib-src"
  "${VENDOR_ROOT}/stubs"
  "${AETHER_CPP_ROOT}/include"
  /opt/homebrew/include
  /opt/homebrew/include/eigen3)
target_compile_options(live_order_stored_match_replay_exe PRIVATE -O3 -w)
target_link_libraries(live_order_stored_match_replay_exe PRIVATE
  aether_glomap_core
  /opt/homebrew/lib/libceres.dylib
  /opt/homebrew/lib/libglog.dylib
  sqlite3)
