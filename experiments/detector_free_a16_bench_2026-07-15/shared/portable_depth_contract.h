#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace pocketworld::depth_sweep {

struct ParityThresholds {
    std::size_t valid_mismatch_max = 0;
    std::size_t accepted_mismatch_max = 0;
    std::size_t accepted_best_index_mismatch_max = 0;
    std::size_t views_mismatch_max = 0;
    double score_mean_abs_max = 0.002;
    double score_max_abs_max = 0.02;
};

struct ParityMetrics {
    std::size_t valid_mismatch_count = 0;
    std::size_t accepted_mismatch_count = 0;
    std::size_t accepted_best_index_mismatch_count = 0;
    std::size_t all_valid_best_index_mismatch_count = 0;
    std::size_t views_mismatch_count = 0;
    std::size_t compared_score_pixels = 0;
    std::size_t actual_accepted_pixels = 0;
    double best_score_mean_abs = 0.0;
    double best_score_max_abs = 0.0;
    double second_score_mean_abs = 0.0;
    double second_score_max_abs = 0.0;

    [[nodiscard]] bool passes(const ParityThresholds& thresholds = {}) const {
        return valid_mismatch_count <= thresholds.valid_mismatch_max &&
            accepted_mismatch_count <= thresholds.accepted_mismatch_max &&
            accepted_best_index_mismatch_count <=
                thresholds.accepted_best_index_mismatch_max &&
            views_mismatch_count <= thresholds.views_mismatch_max &&
            best_score_mean_abs <= thresholds.score_mean_abs_max &&
            best_score_max_abs <= thresholds.score_max_abs_max &&
            second_score_mean_abs <= thresholds.score_mean_abs_max &&
            second_score_max_abs <= thresholds.score_max_abs_max;
    }
};

// A rejected depth candidate has no product point identity. Its argmax is kept
// as a diagnostic, while accepted point births and their depth identities are
// the cross-backend invariant. This prevents harmless floating-point tie swaps
// from weakening the zero-tolerance contract for points that actually exist.
inline ParityMetrics evaluate_parity(
    std::size_t pixel_count,
    const std::uint16_t* expected_best_index,
    const float* expected_best_score,
    const float* expected_second_score,
    const std::uint8_t* expected_views,
    const std::uint8_t* expected_accepted,
    const std::uint16_t* actual_best_index,
    const float* actual_best_score,
    const float* actual_second_score,
    const std::uint8_t* actual_views,
    const std::uint8_t* actual_accepted) {
    ParityMetrics metrics;
    double best_abs_sum = 0.0;
    double second_abs_sum = 0.0;
    for (std::size_t index = 0; index < pixel_count; ++index) {
        const bool expected_valid = expected_best_score[index] > -1.5f;
        const bool actual_valid = actual_best_score[index] > -1.5f;
        if (expected_valid != actual_valid) ++metrics.valid_mismatch_count;
        if (expected_accepted[index] != actual_accepted[index]) {
            ++metrics.accepted_mismatch_count;
        }
        if (actual_accepted[index]) ++metrics.actual_accepted_pixels;
        if (expected_accepted[index] && actual_accepted[index] &&
            expected_best_index[index] != actual_best_index[index]) {
            ++metrics.accepted_best_index_mismatch_count;
        }
        if (!expected_valid || !actual_valid) continue;
        if (expected_best_index[index] != actual_best_index[index]) {
            ++metrics.all_valid_best_index_mismatch_count;
        }
        if (expected_views[index] != actual_views[index]) {
            ++metrics.views_mismatch_count;
        }
        const double best_difference = std::fabs(
            static_cast<double>(expected_best_score[index]) - actual_best_score[index]);
        const double second_difference = std::fabs(
            static_cast<double>(expected_second_score[index]) - actual_second_score[index]);
        best_abs_sum += best_difference;
        second_abs_sum += second_difference;
        metrics.best_score_max_abs = std::max(metrics.best_score_max_abs, best_difference);
        metrics.second_score_max_abs = std::max(
            metrics.second_score_max_abs, second_difference);
        ++metrics.compared_score_pixels;
    }
    if (metrics.compared_score_pixels != 0) {
        metrics.best_score_mean_abs =
            best_abs_sum / static_cast<double>(metrics.compared_score_pixels);
        metrics.second_score_mean_abs =
            second_abs_sum / static_cast<double>(metrics.compared_score_pixels);
    }
    return metrics;
}

}  // namespace pocketworld::depth_sweep
