#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <functional>
#include <limits>
#include <utility>
#include <vector>

namespace pocketworld::wall_planesweep {

struct CliqueResult {
    std::vector<int> members;
    double median = -std::numeric_limits<double>::infinity();
};

inline double median(std::vector<double> values) {
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    const std::size_t middle = values.size() / 2;
    return values.size() % 2 ? values[middle]
                             : (values[middle - 1] + values[middle]) * 0.5;
}

inline CliqueResult largest_consistent_clique(
    const std::vector<double>& ncc, int count, double threshold, int minimum) {
    CliqueResult best;
    if (count < minimum || count > 63 || ncc.size() != static_cast<std::size_t>(count * count)) {
        return best;
    }
    std::vector<std::uint64_t> neighbors(static_cast<std::size_t>(count), 0);
    for (int row = 0; row < count; ++row) {
        for (int column = 0; column < count; ++column) {
            if (row != column && ncc[static_cast<std::size_t>(row * count + column)] >= threshold) {
                neighbors[static_cast<std::size_t>(row)] |= std::uint64_t{1} << column;
            }
        }
    }
    std::vector<int> current;
    const auto consider = [&]() {
        if (current.size() < static_cast<std::size_t>(minimum) ||
            current.size() < best.members.size()) {
            return;
        }
        std::vector<double> pairs;
        for (std::size_t a = 0; a < current.size(); ++a) {
            for (std::size_t b = a + 1; b < current.size(); ++b) {
                pairs.push_back(ncc[static_cast<std::size_t>(current[a] * count + current[b])]);
            }
        }
        const double value = median(std::move(pairs));
        if (current.size() > best.members.size() || value > best.median) {
            best.members = current;
            best.median = value;
        }
    };
    std::function<void(std::uint64_t)> search = [&](std::uint64_t candidates) {
        const std::size_t required = std::max<std::size_t>(minimum, best.members.size());
        if (current.size() + static_cast<std::size_t>(__builtin_popcountll(candidates)) < required) {
            return;
        }
        if (candidates == 0) {
            consider();
            return;
        }
        std::uint64_t remaining = candidates;
        while (remaining) {
            const std::size_t loop_required =
                std::max<std::size_t>(minimum, best.members.size());
            if (current.size() + static_cast<std::size_t>(__builtin_popcountll(remaining)) <
                loop_required) {
                break;
            }
            const std::uint64_t lowest = remaining & (~remaining + 1);
            const int vertex = __builtin_ctzll(lowest);
            current.push_back(vertex);
            search(remaining & neighbors[static_cast<std::size_t>(vertex)]);
            current.pop_back();
            remaining &= ~lowest;
        }
    };
    search((std::uint64_t{1} << count) - 1);
    return best;
}

inline std::pair<bool, double> unique_depth_winner(
    int center_views,
    double center_ncc,
    const std::vector<std::pair<int, double>>& alternatives,
    double required_margin) {
    if (alternatives.empty()) {
        return {true, std::numeric_limits<double>::infinity()};
    }
    double best_alternative = -std::numeric_limits<double>::infinity();
    bool unique = true;
    for (const auto& [views, ncc] : alternatives) {
        best_alternative = std::max(best_alternative, ncc);
        unique = unique && center_views >= views && center_ncc >= ncc + required_margin;
    }
    return {unique, center_ncc - best_alternative};
}

}  // namespace pocketworld::wall_planesweep
