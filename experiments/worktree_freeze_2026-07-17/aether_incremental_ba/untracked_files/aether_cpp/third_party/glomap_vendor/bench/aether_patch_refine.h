#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>

namespace aether_patch {

struct GrayImageView {
  const uint8_t* data = nullptr;
  int width = 0;
  int height = 0;
  int stride = 0;
};

struct GrayImage {
  std::vector<uint8_t> pixels;
  int width = 0;
  int height = 0;

  GrayImageView View() const {
    return {pixels.data(), width, height, width};
  }
};

struct AlignOptions {
  int patch_radius = 7;
  int max_iterations = 20;
  double max_shift_px = 2.0;
  double max_step_px = 0.75;
  double convergence_px = 0.01;
  double min_hessian_eigenvalue = 0.01;
  double max_zero_mean_abs_error = 20.0;
};

struct AlignResult {
  bool ok = false;
  double x = 0.0;
  double y = 0.0;
  double shift_px = 0.0;
  double zero_mean_abs_error = std::numeric_limits<double>::infinity();
  int iterations = 0;
};

inline bool Bilinear(const GrayImageView& image, const double x,
                     const double y, double* value) {
  if (image.data == nullptr || image.width <= 1 || image.height <= 1 ||
      image.stride < image.width || x < 0.0 || y < 0.0 ||
      x >= static_cast<double>(image.width - 1) ||
      y >= static_cast<double>(image.height - 1)) {
    return false;
  }
  const int x0 = static_cast<int>(std::floor(x));
  const int y0 = static_cast<int>(std::floor(y));
  const double ax = x - x0;
  const double ay = y - y0;
  const uint8_t* row0 = image.data + y0 * image.stride;
  const uint8_t* row1 = row0 + image.stride;
  *value = (1.0 - ay) * ((1.0 - ax) * row0[x0] + ax * row0[x0 + 1]) +
           ay * ((1.0 - ax) * row1[x0] + ax * row1[x0 + 1]);
  return true;
}

inline int Reflect101(int value, const int size) {
  if (size <= 1) return 0;
  while (value < 0 || value >= size) {
    if (value < 0) {
      value = -value;
    } else {
      value = 2 * size - value - 2;
    }
  }
  return value;
}

// OpenCV-compatible 5-tap Gaussian reduction kernel [1 4 6 4 1] / 16 in
// each dimension.  Building the pyramid once per image keeps the hot
// correspondence loop allocation-free.
inline GrayImage GaussianHalf(const GrayImageView& input) {
  GrayImage output;
  if (input.data == nullptr || input.width <= 1 || input.height <= 1 ||
      input.stride < input.width) {
    return output;
  }
  output.width = (input.width + 1) / 2;
  output.height = (input.height + 1) / 2;
  output.pixels.resize(static_cast<size_t>(output.width) * output.height);
  constexpr int kernel[5] = {1, 4, 6, 4, 1};
  for (int y = 0; y < output.height; ++y) {
    const int source_y = 2 * y;
    for (int x = 0; x < output.width; ++x) {
      const int source_x = 2 * x;
      int sum = 0;
      for (int ky = -2; ky <= 2; ++ky) {
        const int iy = Reflect101(source_y + ky, input.height);
        const uint8_t* row = input.data + iy * input.stride;
        for (int kx = -2; kx <= 2; ++kx) {
          const int ix = Reflect101(source_x + kx, input.width);
          sum += kernel[ky + 2] * kernel[kx + 2] * row[ix];
        }
      }
      output.pixels[static_cast<size_t>(y) * output.width + x] =
          static_cast<uint8_t>((sum + 128) >> 8);
    }
  }
  return output;
}

// Translation-only, zero-mean direct alignment.  It deliberately operates on
// raw grayscale patches and has no platform API dependency, so the exact core
// is usable by iOS, Android, HarmonyOS, WebAssembly, and the host verifier.
inline AlignResult AlignTranslation(const GrayImageView& source,
                                    const double source_x,
                                    const double source_y,
                                    const GrayImageView& target,
                                    const double target_x,
                                    const double target_y,
                                    const AlignOptions& options = {}) {
  AlignResult result;
  result.x = target_x;
  result.y = target_y;
  if (options.patch_radius < 2 || options.max_iterations <= 0 ||
      options.max_shift_px <= 0.0) {
    return result;
  }

  const int diameter = 2 * options.patch_radius + 1;
  const int count = diameter * diameter;
  std::vector<double> source_patch;
  source_patch.reserve(count);
  double source_mean = 0.0;
  for (int dy = -options.patch_radius; dy <= options.patch_radius; ++dy) {
    for (int dx = -options.patch_radius; dx <= options.patch_radius; ++dx) {
      double value = 0.0;
      if (!Bilinear(source, source_x + dx, source_y + dy, &value)) {
        return result;
      }
      source_patch.push_back(value);
      source_mean += value;
    }
  }
  source_mean /= count;

  double offset_x = 0.0;
  double offset_y = 0.0;
  std::vector<double> target_patch(count);
  std::vector<double> gradient_x(count);
  std::vector<double> gradient_y(count);
  for (int iteration = 0; iteration < options.max_iterations; ++iteration) {
    double target_mean = 0.0;
    double gradient_mean_x = 0.0;
    double gradient_mean_y = 0.0;
    int index = 0;
    for (int dy = -options.patch_radius; dy <= options.patch_radius; ++dy) {
      for (int dx = -options.patch_radius; dx <= options.patch_radius;
           ++dx, ++index) {
        const double x = target_x + offset_x + dx;
        const double y = target_y + offset_y + dy;
        double center = 0.0;
        double left = 0.0;
        double right = 0.0;
        double up = 0.0;
        double down = 0.0;
        if (!Bilinear(target, x, y, &center) ||
            !Bilinear(target, x - 1.0, y, &left) ||
            !Bilinear(target, x + 1.0, y, &right) ||
            !Bilinear(target, x, y - 1.0, &up) ||
            !Bilinear(target, x, y + 1.0, &down)) {
          return result;
        }
        target_patch[index] = center;
        gradient_x[index] = 0.5 * (right - left);
        gradient_y[index] = 0.5 * (down - up);
        target_mean += center;
        gradient_mean_x += gradient_x[index];
        gradient_mean_y += gradient_y[index];
      }
    }
    target_mean /= count;
    gradient_mean_x /= count;
    gradient_mean_y /= count;

    double hxx = 0.0;
    double hxy = 0.0;
    double hyy = 0.0;
    double bx = 0.0;
    double by = 0.0;
    double absolute_error = 0.0;
    for (int i = 0; i < count; ++i) {
      const double residual =
          (target_patch[i] - target_mean) - (source_patch[i] - source_mean);
      const double jx = gradient_x[i] - gradient_mean_x;
      const double jy = gradient_y[i] - gradient_mean_y;
      hxx += jx * jx;
      hxy += jx * jy;
      hyy += jy * jy;
      bx += jx * residual;
      by += jy * residual;
      absolute_error += std::abs(residual);
    }
    const double determinant = hxx * hyy - hxy * hxy;
    const double trace = hxx + hyy;
    const double discriminant =
        std::max(0.0, trace * trace - 4.0 * determinant);
    const double min_eigenvalue =
        0.5 * (trace - std::sqrt(discriminant)) / count;
    if (!std::isfinite(determinant) || determinant <= 1e-12 ||
        min_eigenvalue < options.min_hessian_eigenvalue) {
      return result;
    }

    double step_x = -(hyy * bx - hxy * by) / determinant;
    double step_y = -(-hxy * bx + hxx * by) / determinant;
    const double step_norm = std::hypot(step_x, step_y);
    if (!std::isfinite(step_norm)) return result;
    if (step_norm > options.max_step_px) {
      const double scale = options.max_step_px / step_norm;
      step_x *= scale;
      step_y *= scale;
    }
    offset_x += step_x;
    offset_y += step_y;
    result.iterations = iteration + 1;
    result.zero_mean_abs_error = absolute_error / count;
    if (std::hypot(offset_x, offset_y) > options.max_shift_px) return result;
    if (std::hypot(step_x, step_y) <= options.convergence_px) break;
  }

  result.x = target_x + offset_x;
  result.y = target_y + offset_y;
  result.shift_px = std::hypot(offset_x, offset_y);
  result.ok = std::isfinite(result.zero_mean_abs_error) &&
              result.zero_mean_abs_error <=
                  options.max_zero_mean_abs_error;
  return result;
}

// Coarse-to-fine translation refinement.  Match identities remain fixed: the
// pyramid only finds a subpixel correction to the two stored observations.
// The full-resolution displacement is bounded after every level so a coarse
// local minimum can never expand the match search radius.
inline AlignResult AlignPyramidalTranslation(
    const std::vector<GrayImageView>& source_pyramid, const double source_x,
    const double source_y,
    const std::vector<GrayImageView>& target_pyramid, const double target_x,
    const double target_y, const AlignOptions& options = {}) {
  AlignResult result;
  result.x = target_x;
  result.y = target_y;
  if (source_pyramid.empty() ||
      source_pyramid.size() != target_pyramid.size()) {
    return result;
  }

  double correction_x = 0.0;
  double correction_y = 0.0;
  int total_iterations = 0;
  double final_error = std::numeric_limits<double>::infinity();
  for (int level = static_cast<int>(source_pyramid.size()) - 1; level >= 0;
       --level) {
    const double scale = std::ldexp(1.0, level);
    AlignOptions level_options = options;
    level_options.max_shift_px = options.max_shift_px / scale;
    level_options.max_step_px =
        std::min(options.max_step_px, level_options.max_shift_px);
    level_options.convergence_px = options.convergence_px / scale;
    const auto level_result = AlignTranslation(
        source_pyramid[level], source_x / scale, source_y / scale,
        target_pyramid[level], target_x / scale + correction_x,
        target_y / scale + correction_y, level_options);
    if (!level_result.ok) return result;
    total_iterations += level_result.iterations;
    final_error = level_result.zero_mean_abs_error;
    correction_x = level_result.x - target_x / scale;
    correction_y = level_result.y - target_y / scale;
    if (std::hypot(correction_x * scale, correction_y * scale) >
        options.max_shift_px) {
      return result;
    }
    if (level > 0) {
      correction_x *= 2.0;
      correction_y *= 2.0;
    }
  }

  result.ok = true;
  result.x = target_x + correction_x;
  result.y = target_y + correction_y;
  result.shift_px = std::hypot(correction_x, correction_y);
  result.zero_mean_abs_error = final_error;
  result.iterations = total_iterations;
  return result;
}

}  // namespace aether_patch
