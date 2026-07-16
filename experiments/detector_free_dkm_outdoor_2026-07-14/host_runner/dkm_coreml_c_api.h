#ifndef POCKETWORLD_DKM_COREML_C_API_H
#define POCKETWORLD_DKM_COREML_C_API_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct pw_dkm_coreml_context pw_dkm_coreml_context;

typedef struct pw_dkm_coreml_result {
    float* flow;
    size_t flow_count;
    float* certainty;
    size_t certainty_count;
    float* low_certainty;
    size_t low_certainty_count;
    double inference_seconds;
} pw_dkm_coreml_result;

int pw_dkm_coreml_create(
    const char* compiled_model_path,
    pw_dkm_coreml_context** out_context,
    char* error_message,
    size_t error_capacity);

uint32_t pw_dkm_coreml_input_width(const pw_dkm_coreml_context* context);
uint32_t pw_dkm_coreml_input_height(const pw_dkm_coreml_context* context);

int pw_dkm_coreml_predict(
    pw_dkm_coreml_context* context,
    const float* image0_nchw,
    const float* image1_nchw,
    size_t input_float_count,
    pw_dkm_coreml_result* out_result,
    char* error_message,
    size_t error_capacity);

void pw_dkm_coreml_result_release(pw_dkm_coreml_result* result);
void pw_dkm_coreml_destroy(pw_dkm_coreml_context* context);

#ifdef __cplusplus
}
#endif

#endif
