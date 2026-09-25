# Minimal replica of aether_cpp/CMakeLists.txt @a313ede0 "P3a1 OFFICIAL GPU CARRIER" (lines 485-560)
# + the WGSL bake (lines 225-271), so the Xcode generator emits the same target-level settings
# without configuring Dawn. Source root = AETHER_SRC (local clone); Dawn headers read-only from the
# shared tree (same files the shipped carrier was compiled against).
cmake_minimum_required(VERSION 3.22)
project(aether3d_cpp_core VERSION 0.1.0 LANGUAGES C CXX)
enable_language(OBJCXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(A "${AETHER_SRC}")
set(AETHER_WGSL_SOURCE_DIR ${A}/shaders/wgsl)
set(AETHER_WGSL_GENERATED_DIR ${CMAKE_BINARY_DIR}/generated/aether/shaders)
file(MAKE_DIRECTORY ${AETHER_WGSL_GENERATED_DIR})
file(GLOB AETHER_WGSL_FILES "${AETHER_WGSL_SOURCE_DIR}/*.wgsl")
set(AETHER_WGSL_GENERATED_CPPS "")
foreach(wgsl ${AETHER_WGSL_FILES})
    get_filename_component(wgsl_name ${wgsl} NAME_WE)
    set(generated_cpp ${AETHER_WGSL_GENERATED_DIR}/${wgsl_name}_wgsl.cpp)
    add_custom_command(
        OUTPUT ${generated_cpp}
        COMMAND ${CMAKE_COMMAND} -DINPUT=${wgsl} -DOUTPUT=${generated_cpp} -DNAME=${wgsl_name}
            -P ${A}/scripts/bake_one_wgsl.cmake
        DEPENDS ${wgsl} ${A}/scripts/bake_one_wgsl.cmake
        VERBATIM)
    list(APPEND AETHER_WGSL_GENERATED_CPPS ${generated_cpp})
endforeach()
add_custom_target(aether_bake_wgsl ALL DEPENDS ${AETHER_WGSL_GENERATED_CPPS})
set(AETHER_PWOFFICIAL_DAWN_GEN_INCLUDE_DIR "${DAWN_GEN_INCLUDE}")
set(AETHER_DAWN_SRC_INCLUDE_DIR "${DAWN_SRC_INCLUDE}")
# aether_cpp/CMakeLists.txt @a313ede0 lines 450-456 [PIPE-BD 2026-09-11]: directory-level property,
# Dawn is built -fno-rtti so the one dawn::platform::Platform subclass must be too.
set_source_files_properties(${A}/tools/dawn_histogram_sink.cpp PROPERTIES COMPILE_OPTIONS "-fno-rtti")
add_library(pwofficial_gpu_extract STATIC
    ${A}/third_party/glomap_vendor/bench/dsp_sift_gpu_c.cc
    ${A}/src/sfm/canonical_feature_selector_v1.cc
    ${A}/tools/sift_extract_dawn.cc
    ${A}/tools/sift_pyramid_dawn.cc
    ${A}/tools/dawn_kernel_harness.cpp
    ${A}/tools/dawn_histogram_sink.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_gray_to_f32_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_gss_blur_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_gss_blur_fused_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_gss_resample_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_dog_detect_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_dog_detect_compact_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_dog_refine_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_dog_cand_reset_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_nonextrema_suppress_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_suppress_grid_count_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_suppress_grid_scan_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_suppress_grid_scatter_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_suppress_grid_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_affine_shape_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_orientation_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_orientation_atomic_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_dsp_descriptor_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_dsp_descriptor_f16_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_dsp_descriptor_f16_atomic_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_dsp_descriptor_par_wgsl.cpp
    ${AETHER_WGSL_GENERATED_DIR}/sift_dsp_mean_wgsl.cpp)
target_include_directories(pwofficial_gpu_extract PRIVATE
    ${A}/tools ${A}/include ${A}/official_pipeline/src ${A}/third_party/stb
    ${A}/third_party/glomap_vendor/colmap-src ${A}/third_party/glomap_vendor/stubs
    ${A}/third_party/glog-install/include ${A}/third_party/ceres/include
    ${A}/third_party/ceres-build-ios/include ${A}/third_party/ceres/config
    ${A}/third_party/eigen-install/include/eigen3
    ${AETHER_DAWN_SRC_INCLUDE_DIR} ${AETHER_PWOFFICIAL_DAWN_GEN_INCLUDE_DIR})
target_compile_definitions(pwofficial_gpu_extract PRIVATE
    AETHER_FEATURE_SELECTION_ENV_OFFICIAL=1
    AETHER_GPU_TIMESTAMPS_ENV_OFFICIAL=1
    AETHER_GPU_TIMESTAMP_DAWN_REVISION="12ee391c7411285895f4289a3d889a182c093014"
    AETHER_GPU_TIMESTAMP_DAWN_ARTIFACT_SHA256="625cf65dded708ad1abd3dc92f3b47c3c90c384f508676b56303f9341d301b42"
    EIGEN_MPL2_ONLY GLOG_USE_GLOG_EXPORT GLOG_NO_ABBREVIATED_SEVERITIES
    GLOG_VERSION_MAJOR=0 GLOG_VERSION_MINOR=7)
target_compile_options(pwofficial_gpu_extract PRIVATE -O2 -w)
add_dependencies(pwofficial_gpu_extract aether_bake_wgsl)
set_target_properties(pwofficial_gpu_extract PROPERTIES OUTPUT_NAME pwofficial_gpu_extract)
