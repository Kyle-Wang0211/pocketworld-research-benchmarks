#import <CoreML/CoreML.h>
#import <Foundation/Foundation.h>

#include "dkm_coreml_c_api.h"

#include <chrono>
#include <cstring>
#include <new>
#include <string>
#include <vector>

struct pw_dkm_coreml_context {
    MLModel* model{nil};
    NSString* flow_key{nil};
    NSString* certainty_key{nil};
    NSString* low_certainty_key{nil};
    uint32_t width{0};
    uint32_t height{0};
};

namespace {

void set_error(char* destination, size_t capacity, const std::string& message) {
    if (!destination || capacity == 0) return;
    std::strncpy(destination, message.c_str(), capacity - 1);
    destination[capacity - 1] = '\0';
}

std::vector<size_t> dimensions(NSArray<NSNumber*>* shape) {
    std::vector<size_t> values;
    values.reserve(shape.count);
    for (NSNumber* value in shape) {
        values.push_back(static_cast<size_t>(value.unsignedLongLongValue));
    }
    return values;
}

size_t element_count(const std::vector<size_t>& shape) {
    size_t count = 1;
    for (size_t value : shape) count *= value;
    return count;
}

bool copy_multi_array(
    MLMultiArray* array,
    float** destination,
    size_t* destination_count,
    std::string& error) {
    if (!array || array.dataType != MLMultiArrayDataTypeFloat32) {
        error = "output is missing or is not float32";
        return false;
    }
    const auto shape = dimensions(array.shape);
    const auto strides = dimensions(array.strides);
    const size_t count = element_count(shape);
    float* copied = new (std::nothrow) float[count];
    if (!copied) {
        error = "output allocation failed";
        return false;
    }
    const float* source = static_cast<const float*>(array.dataPointer);
    for (size_t linear = 0; linear < count; ++linear) {
        size_t remainder = linear;
        size_t offset = 0;
        for (size_t dimension = shape.size(); dimension-- > 0;) {
            const size_t index = remainder % shape[dimension];
            remainder /= shape[dimension];
            offset += index * strides[dimension];
        }
        copied[linear] = source[offset];
    }
    *destination = copied;
    *destination_count = count;
    return true;
}

MLMultiArray* make_input(
    const float* source,
    uint32_t height,
    uint32_t width,
    NSError** error) {
    NSArray<NSNumber*>* shape = @[@1, @3, @(height), @(width)];
    MLMultiArray* array = [[MLMultiArray alloc]
        initWithShape:shape
        dataType:MLMultiArrayDataTypeFloat32
        error:error];
    if (!array) return nil;
    const size_t count = static_cast<size_t>(3) * height * width;
    std::memcpy(array.dataPointer, source, count * sizeof(float));
    return array;
}

bool configure_description(
    pw_dkm_coreml_context* context,
    std::string& error) {
    NSDictionary<NSString*, MLFeatureDescription*>* inputs =
        context->model.modelDescription.inputDescriptionsByName;
    for (NSString* key in @[@"image0", @"image1"]) {
        MLFeatureDescription* feature = inputs[key];
        if (!feature || feature.type != MLFeatureTypeMultiArray) {
            error = "model must expose float multi-array inputs image0 and image1";
            return false;
        }
        const auto shape = dimensions(feature.multiArrayConstraint.shape);
        if (shape.size() != 4 || shape[0] != 1 || shape[1] != 3) {
            error = "unexpected CoreML input shape";
            return false;
        }
        if (context->width == 0) {
            context->height = static_cast<uint32_t>(shape[2]);
            context->width = static_cast<uint32_t>(shape[3]);
        } else if (shape[2] != context->height || shape[3] != context->width) {
            error = "CoreML input shapes disagree";
            return false;
        }
    }

    NSDictionary<NSString*, MLFeatureDescription*>* outputs =
        context->model.modelDescription.outputDescriptionsByName;
    for (NSString* key in outputs) {
        MLFeatureDescription* feature = outputs[key];
        if (feature.type != MLFeatureTypeMultiArray) continue;
        const auto shape = dimensions(feature.multiArrayConstraint.shape);
        if (shape.size() != 4 || shape[0] != 2) continue;
        if (shape[1] == 2 && shape[2] == context->height && shape[3] == context->width) {
            context->flow_key = key;
        } else if (
            shape[1] == 1 && shape[2] == context->height && shape[3] == context->width) {
            context->certainty_key = key;
        } else if (
            shape[1] == 1 && shape[2] * 16 == context->height &&
            shape[3] * 16 == context->width) {
            context->low_certainty_key = key;
        }
    }
    if (!context->flow_key || !context->certainty_key || !context->low_certainty_key) {
        error = "model does not expose the expected DKM flow/certainty outputs";
        return false;
    }
    return true;
}

}  // namespace

int pw_dkm_coreml_create(
    const char* compiled_model_path,
    pw_dkm_coreml_context** out_context,
    char* error_message,
    size_t error_capacity) {
    if (!compiled_model_path || !out_context) {
        set_error(error_message, error_capacity, "invalid create arguments");
        return 1;
    }
    *out_context = nullptr;
    @autoreleasepool {
        pw_dkm_coreml_context* context = new (std::nothrow) pw_dkm_coreml_context();
        if (!context) {
            set_error(error_message, error_capacity, "context allocation failed");
            return 2;
        }
        NSString* path = [NSString stringWithUTF8String:compiled_model_path];
        NSURL* url = [NSURL fileURLWithPath:path isDirectory:YES];
        MLModelConfiguration* configuration = [[MLModelConfiguration alloc] init];
        configuration.computeUnits = MLComputeUnitsCPUAndGPU;
        NSError* load_error = nil;
        context->model = [MLModel modelWithContentsOfURL:url
                                           configuration:configuration
                                                   error:&load_error];
        if (!context->model) {
            const char* reason = load_error.localizedDescription.UTF8String;
            set_error(error_message, error_capacity, reason ? reason : "model load failed");
            delete context;
            return 3;
        }
        std::string description_error;
        if (!configure_description(context, description_error)) {
            set_error(error_message, error_capacity, description_error);
            delete context;
            return 4;
        }
        *out_context = context;
        return 0;
    }
}

uint32_t pw_dkm_coreml_input_width(const pw_dkm_coreml_context* context) {
    return context ? context->width : 0;
}

uint32_t pw_dkm_coreml_input_height(const pw_dkm_coreml_context* context) {
    return context ? context->height : 0;
}

int pw_dkm_coreml_predict(
    pw_dkm_coreml_context* context,
    const float* image0_nchw,
    const float* image1_nchw,
    size_t input_float_count,
    pw_dkm_coreml_result* out_result,
    char* error_message,
    size_t error_capacity) {
    if (!context || !image0_nchw || !image1_nchw || !out_result) {
        set_error(error_message, error_capacity, "invalid predict arguments");
        return 1;
    }
    const size_t expected = static_cast<size_t>(3) * context->height * context->width;
    if (input_float_count != expected) {
        set_error(error_message, error_capacity, "input float count mismatch");
        return 2;
    }
    *out_result = {};
    @autoreleasepool {
        NSError* array_error = nil;
        MLMultiArray* image0 = make_input(
            image0_nchw, context->height, context->width, &array_error);
        MLMultiArray* image1 = make_input(
            image1_nchw, context->height, context->width, &array_error);
        if (!image0 || !image1) {
            const char* reason = array_error.localizedDescription.UTF8String;
            set_error(error_message, error_capacity, reason ? reason : "input allocation failed");
            return 3;
        }
        NSDictionary<NSString*, MLFeatureValue*>* dictionary = @{
            @"image0": [MLFeatureValue featureValueWithMultiArray:image0],
            @"image1": [MLFeatureValue featureValueWithMultiArray:image1],
        };
        NSError* provider_error = nil;
        MLDictionaryFeatureProvider* provider = [[MLDictionaryFeatureProvider alloc]
            initWithDictionary:dictionary
            error:&provider_error];
        if (!provider) {
            const char* reason = provider_error.localizedDescription.UTF8String;
            set_error(error_message, error_capacity, reason ? reason : "provider failed");
            return 4;
        }
        NSError* prediction_error = nil;
        const auto started = std::chrono::steady_clock::now();
        id<MLFeatureProvider> output = [context->model predictionFromFeatures:provider
                                                                       error:&prediction_error];
        const auto finished = std::chrono::steady_clock::now();
        if (!output) {
            const char* reason = prediction_error.localizedDescription.UTF8String;
            set_error(error_message, error_capacity, reason ? reason : "prediction failed");
            return 5;
        }
        std::string copy_error;
        if (!copy_multi_array(
                [output featureValueForName:context->flow_key].multiArrayValue,
                &out_result->flow,
                &out_result->flow_count,
                copy_error) ||
            !copy_multi_array(
                [output featureValueForName:context->certainty_key].multiArrayValue,
                &out_result->certainty,
                &out_result->certainty_count,
                copy_error) ||
            !copy_multi_array(
                [output featureValueForName:context->low_certainty_key].multiArrayValue,
                &out_result->low_certainty,
                &out_result->low_certainty_count,
                copy_error)) {
            pw_dkm_coreml_result_release(out_result);
            set_error(error_message, error_capacity, copy_error);
            return 6;
        }
        out_result->inference_seconds =
            std::chrono::duration<double>(finished - started).count();
        return 0;
    }
}

void pw_dkm_coreml_result_release(pw_dkm_coreml_result* result) {
    if (!result) return;
    delete[] result->flow;
    delete[] result->certainty;
    delete[] result->low_certainty;
    *result = {};
}

void pw_dkm_coreml_destroy(pw_dkm_coreml_context* context) {
    delete context;
}
