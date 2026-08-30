include_guard(GLOBAL)

function(add_basalt_vio_core target_name)
  if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "${target_name} is an iOS-only build target")
  endif()
  if(NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
    message(FATAL_ERROR
      "${target_name} requires CMAKE_OSX_ARCHITECTURES=arm64; got '${CMAKE_OSX_ARCHITECTURES}'")
  endif()

  get_filename_component(_bench_root "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/.." ABSOLUTE)
  set(_basalt_root "${_bench_root}/Vendor/basalt")
  set(_headers_root "${_bench_root}/Vendor/basalt-headers")
  set(_source_manifest "${_bench_root}/Vendor/basalt_vio_source_allowlist.tsv")

  foreach(_required_path IN ITEMS
      "${_basalt_root}/include"
      "${_headers_root}/CMakeLists.txt"
      "${_source_manifest}")
    if(NOT EXISTS "${_required_path}")
      message(FATAL_ERROR "Missing verified vendor input: ${_required_path}")
    endif()
  endforeach()

  find_package(Eigen3 5.0 CONFIG REQUIRED)
  find_package(TBB CONFIG REQUIRED)
  find_package(OpenCV CONFIG REQUIRED COMPONENTS core imgproc features2d calib3d)
  find_package(fmt CONFIG REQUIRED)
  find_package(magic_enum CONFIG REQUIRED)
  find_package(nlohmann_json CONFIG REQUIRED)
  find_package(opengv CONFIG REQUIRED)
  find_package(Sophus CONFIG REQUIRED)
  find_package(cereal CONFIG REQUIRED)

  if(NOT TARGET basalt::basalt-headers)
    add_library(basalt_vio_vendor_headers INTERFACE)
    add_library(basalt::basalt-headers ALIAS basalt_vio_vendor_headers)
    target_include_directories(basalt_vio_vendor_headers INTERFACE
      "${_headers_root}/include")
    target_link_libraries(basalt_vio_vendor_headers INTERFACE
      Eigen3::Eigen
      Sophus::Sophus
      cereal::cereal)
    target_compile_features(basalt_vio_vendor_headers INTERFACE cxx_std_17)
  endif()

  file(STRINGS "${_source_manifest}" _allowlist_rows)
  set(_basalt_sources "")
  foreach(_row IN LISTS _allowlist_rows)
    if(_row MATCHES "^[ \t]*#" OR _row STREQUAL "")
      continue()
    endif()
    string(REGEX MATCH "^[0-9a-f]+[\t]+(.+)$" _matched "${_row}")
    if(NOT _matched)
      message(FATAL_ERROR "Malformed source allowlist row: ${_row}")
    endif()
    set(_relative_source "${CMAKE_MATCH_1}")
    if(NOT _relative_source MATCHES "^src/(linearization|optical_flow|utils|vi_estimator)/")
      message(FATAL_ERROR "Source is outside the frozen VIO slice: ${_relative_source}")
    endif()
    list(APPEND _basalt_sources "${_basalt_root}/${_relative_source}")
  endforeach()

  list(LENGTH _basalt_sources _source_count)
  if(NOT _source_count EQUAL 16)
    message(FATAL_ERROR "Frozen VIO slice must contain exactly 16 sources; got ${_source_count}")
  endif()

  add_library(${target_name} STATIC ${_basalt_sources})
  add_library(basalt::vio_core ALIAS ${target_name})
  set_target_properties(${target_name} PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED YES
    CXX_EXTENSIONS NO
    POSITION_INDEPENDENT_CODE YES
    OUTPUT_NAME basalt_vio_core)

  target_include_directories(${target_name} PUBLIC "${_basalt_root}/include")
  target_compile_definitions(${target_name} PUBLIC
    BASALT_INSTANTIATIONS_FLOAT
    EIGEN_DONT_PARALLELIZE)
  if(CMAKE_CXX_COMPILER_ID MATCHES "^(AppleClang|Clang)$")
    target_compile_options(${target_name} PRIVATE
      -Wall
      -Wextra
      -Werror
      -Wno-error=deprecated-declarations
      -Wno-error=unused-parameter
      -Wno-error=unused-variable
      -Wno-error=unused-but-set-variable
      -Wno-missing-template-arg-list-after-template-kw
      -ftemplate-backtrace-limit=0)
  endif()
  target_link_libraries(${target_name}
    PUBLIC
      basalt::basalt-headers
      Eigen3::Eigen
      TBB::tbb
    PRIVATE
      ${OpenCV_LIBS}
      fmt::fmt
      magic_enum::magic_enum
      nlohmann_json::nlohmann_json
      opengv
      Sophus::Sophus
      cereal::cereal)
endfunction()
