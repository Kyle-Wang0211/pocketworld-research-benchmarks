#include "portable_depth_contract.h"

#include <cassert>
#include <cstdint>

using pocketworld::depth_sweep::evaluate_parity;

int main() {
    const std::uint16_t expected_index[] = {4, 7};
    const float expected_best[] = {0.9f, 0.7f};
    const float expected_second[] = {0.8f, 0.6f};
    const std::uint8_t expected_views[] = {4, 4};
    const std::uint8_t expected_accepted[] = {1, 0};

    {
        const std::uint16_t actual_index[] = {4, 8};
        const auto metrics = evaluate_parity(
            2, expected_index, expected_best, expected_second, expected_views,
            expected_accepted, actual_index, expected_best, expected_second,
            expected_views, expected_accepted);
        assert(metrics.all_valid_best_index_mismatch_count == 1);
        assert(metrics.accepted_best_index_mismatch_count == 0);
        assert(metrics.passes());
    }
    {
        const std::uint16_t actual_index[] = {5, 7};
        const auto metrics = evaluate_parity(
            2, expected_index, expected_best, expected_second, expected_views,
            expected_accepted, actual_index, expected_best, expected_second,
            expected_views, expected_accepted);
        assert(metrics.accepted_best_index_mismatch_count == 1);
        assert(!metrics.passes());
    }
    {
        const std::uint8_t actual_accepted[] = {1, 1};
        const auto metrics = evaluate_parity(
            2, expected_index, expected_best, expected_second, expected_views,
            expected_accepted, expected_index, expected_best, expected_second,
            expected_views, actual_accepted);
        assert(metrics.accepted_mismatch_count == 1);
        assert(!metrics.passes());
    }
    return 0;
}
