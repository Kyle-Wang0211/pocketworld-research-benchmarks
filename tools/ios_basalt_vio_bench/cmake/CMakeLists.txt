cmake_minimum_required(VERSION 3.24)

project(BasaltVIOIOSCore LANGUAGES C CXX)

include("${CMAKE_CURRENT_LIST_DIR}/BasaltVIOCore.cmake")
add_basalt_vio_core(basalt_vio_core)

add_executable(basalt_vio_core_link_probe "${CMAKE_CURRENT_LIST_DIR}/link_probe.cpp")
target_link_libraries(basalt_vio_core_link_probe PRIVATE basalt::vio_core)
target_link_options(basalt_vio_core_link_probe PRIVATE
  "LINKER:-force_load,$<TARGET_FILE:basalt_vio_core>")
