#include "wall_scale_rescue_contract.h"

#include <cassert>
#include <cmath>
#include <vector>

int main() {
    using pocketworld::wall_planesweep::largest_consistent_clique;
    using pocketworld::wall_planesweep::unique_depth_winner;
    const std::vector<double> ncc = {
        1.0, 0.9, 0.9, 0.9,
        0.9, 1.0, 0.8, 0.2,
        0.9, 0.8, 1.0, 0.1,
        0.9, 0.2, 0.1, 1.0,
    };
    const auto clique = largest_consistent_clique(ncc, 4, 0.7, 3);
    assert((clique.members == std::vector<int>{0, 1, 2}));
    const auto [clear, margin] = unique_depth_winner(5, 0.93, {{5, 0.86}, {4, 0.87}}, 0.06);
    assert(clear);
    assert(std::abs(margin - 0.06) < 1.0e-12);
    const auto [ambiguous, ignored] = unique_depth_winner(4, 0.91, {{4, 0.90}}, 0.02);
    (void)ignored;
    assert(!ambiguous);
    return 0;
}
