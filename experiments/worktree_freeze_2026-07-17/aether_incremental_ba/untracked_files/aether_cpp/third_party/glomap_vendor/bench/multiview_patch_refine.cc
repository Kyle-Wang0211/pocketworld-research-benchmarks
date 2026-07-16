#include "aether_patch_refine.h"

#include <sqlite3.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;
constexpr int64_t kMaxImageId = 2147483647LL;

struct Options {
  int min_support = 3;
  int pyramid_levels = 2;
  double consensus_radius_px = 0.75;
  double max_final_shift_px = 2.0;
  aether_patch::AlignOptions align;
  std::filesystem::path geometry_db;
};

struct Keypoints {
  int rows = 0;
  int cols = 0;
  std::vector<float> values;
};

struct Image {
  int id = 0;
  int width = 0;
  int height = 0;
  std::vector<uint8_t> gray;
  std::vector<aether_patch::GrayImage> reduced_images;
  std::vector<aether_patch::GrayImageView> pyramid_views;

  aether_patch::GrayImageView View() const {
    return {gray.data(), width, height, width};
  }

  void BuildPyramid(const int max_level) {
    reduced_images.clear();
    pyramid_views.clear();
    reduced_images.reserve(std::max(0, max_level));
    pyramid_views.reserve(std::max(0, max_level) + 1);
    pyramid_views.push_back(View());
    for (int level = 0; level < max_level; ++level) {
      reduced_images.push_back(
          aether_patch::GaussianHalf(pyramid_views.back()));
      if (reduced_images.back().pixels.empty()) {
        throw std::runtime_error("cannot build grayscale pyramid");
      }
      pyramid_views.push_back(reduced_images.back().View());
    }
  }
};

struct Proposal {
  double x = 0.0;
  double y = 0.0;
  double error = 0.0;
  int support_image_id = 0;
};

struct GeometryRow {
  int image_id1 = 0;
  int image_id2 = 0;
  std::vector<std::pair<uint32_t, uint32_t>> matches;
};

void CheckSqlite(const int rc, sqlite3* db, const char* operation) {
  if (rc == SQLITE_OK || rc == SQLITE_DONE || rc == SQLITE_ROW) return;
  throw std::runtime_error(std::string(operation) + ": " +
                           (db ? sqlite3_errmsg(db) : sqlite3_errstr(rc)));
}

int OpenImmutable(const std::filesystem::path& path, sqlite3** database) {
  const std::string uri =
      "file:" + std::filesystem::absolute(path).string() + "?immutable=1";
  return sqlite3_open_v2(uri.c_str(), database,
                         SQLITE_OPEN_READONLY | SQLITE_OPEN_URI, nullptr);
}

void BackupDatabase(const std::filesystem::path& source,
                    const std::filesystem::path& destination) {
  if (std::filesystem::exists(destination)) {
    throw std::runtime_error("refusing to overwrite " + destination.string());
  }
  sqlite3* source_db = nullptr;
  sqlite3* destination_db = nullptr;
  CheckSqlite(OpenImmutable(source, &source_db),
              source_db, "open source database");
  try {
    CheckSqlite(sqlite3_open_v2(destination.string().c_str(), &destination_db,
                                SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE,
                                nullptr),
                destination_db, "open destination database");
    sqlite3_backup* backup =
        sqlite3_backup_init(destination_db, "main", source_db, "main");
    if (backup == nullptr) {
      throw std::runtime_error(std::string("sqlite backup init: ") +
                               sqlite3_errmsg(destination_db));
    }
    const int step = sqlite3_backup_step(backup, -1);
    const int finish = sqlite3_backup_finish(backup);
    if (step != SQLITE_DONE) CheckSqlite(step, destination_db, "sqlite backup");
    CheckSqlite(finish, destination_db, "sqlite backup finish");
  } catch (...) {
    if (destination_db) sqlite3_close(destination_db);
    sqlite3_close(source_db);
    std::filesystem::remove(destination);
    throw;
  }
  sqlite3_close(destination_db);
  sqlite3_close(source_db);
}

std::vector<uint8_t> ReadBytes(const std::filesystem::path& path,
                               const size_t expected_size) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot open " + path.string());
  stream.seekg(0, std::ios::end);
  const size_t size = static_cast<size_t>(stream.tellg());
  stream.seekg(0, std::ios::beg);
  if (size != expected_size) {
    throw std::runtime_error(path.string() + " size=" + std::to_string(size) +
                             " expected=" + std::to_string(expected_size));
  }
  std::vector<uint8_t> bytes(size);
  stream.read(reinterpret_cast<char*>(bytes.data()), bytes.size());
  if (!stream) throw std::runtime_error("short read " + path.string());
  return bytes;
}

std::string JsonStringField(const std::string& line, const std::string& key) {
  const std::string needle = "\"" + key + "\":\"";
  const size_t begin = line.find(needle);
  if (begin == std::string::npos) return {};
  std::string value;
  for (size_t i = begin + needle.size(); i < line.size(); ++i) {
    if (line[i] == '"') break;
    if (line[i] == '\\' && i + 1 < line.size()) ++i;
    value.push_back(line[i]);
  }
  return value;
}

int JsonIntField(const std::string& line, const std::string& key) {
  const std::string needle = "\"" + key + "\":";
  const size_t begin = line.find(needle);
  if (begin == std::string::npos) return -1;
  return static_cast<int>(std::strtol(line.c_str() + begin + needle.size(),
                                      nullptr, 10));
}

std::unordered_map<int, std::filesystem::path> ReadGrayPaths(
    const std::filesystem::path& ledger,
    const std::filesystem::path& gray_dir) {
  std::ifstream stream(ledger);
  if (!stream) throw std::runtime_error("cannot open " + ledger.string());
  std::unordered_map<int, std::filesystem::path> paths;
  std::string line;
  while (std::getline(stream, line)) {
    const int frame_id = JsonIntField(line, "frameId");
    const std::string jpeg = JsonStringField(line, "jpegPath");
    if (frame_id < 0 || jpeg.empty()) continue;
    std::filesystem::path name = std::filesystem::path(jpeg).filename();
    name.replace_extension(".sfm-gray");
    paths[frame_id + 1] = gray_dir / name;
  }
  return paths;
}

std::unordered_map<int, Image> ReadImages(
    sqlite3* db, const std::unordered_map<int, std::filesystem::path>& paths,
    const int pyramid_levels, size_t* gray_bytes) {
  sqlite3_stmt* statement = nullptr;
  CheckSqlite(sqlite3_prepare_v2(
                  db,
                  "SELECT images.image_id, cameras.width, cameras.height "
                  "FROM images JOIN cameras ON images.camera_id = "
                  "cameras.camera_id ORDER BY images.image_id",
                  -1, &statement, nullptr),
              db, "prepare images");
  std::unordered_map<int, Image> images;
  while (sqlite3_step(statement) == SQLITE_ROW) {
    Image image;
    image.id = sqlite3_column_int(statement, 0);
    image.width = sqlite3_column_int(statement, 1);
    image.height = sqlite3_column_int(statement, 2);
    const auto path = paths.find(image.id);
    if (path == paths.end()) {
      sqlite3_finalize(statement);
      throw std::runtime_error("missing grayscale path for image " +
                               std::to_string(image.id));
    }
    image.gray = ReadBytes(path->second,
                           static_cast<size_t>(image.width) * image.height);
    *gray_bytes += image.gray.size();
    image.BuildPyramid(pyramid_levels);
    images.emplace(image.id, std::move(image));
  }
  sqlite3_finalize(statement);
  return images;
}

std::unordered_map<int, Keypoints> ReadKeypoints(sqlite3* db) {
  sqlite3_stmt* statement = nullptr;
  CheckSqlite(sqlite3_prepare_v2(
                  db,
                  "SELECT image_id, rows, cols, data FROM keypoints ORDER BY "
                  "image_id",
                  -1, &statement, nullptr),
              db, "prepare keypoints");
  std::unordered_map<int, Keypoints> keypoints;
  while (sqlite3_step(statement) == SQLITE_ROW) {
    const int image_id = sqlite3_column_int(statement, 0);
    Keypoints row;
    row.rows = sqlite3_column_int(statement, 1);
    row.cols = sqlite3_column_int(statement, 2);
    const void* blob = sqlite3_column_blob(statement, 3);
    const int bytes = sqlite3_column_bytes(statement, 3);
    const size_t expected =
        static_cast<size_t>(row.rows) * row.cols * sizeof(float);
    if (blob == nullptr || bytes != static_cast<int>(expected) || row.cols < 2) {
      sqlite3_finalize(statement);
      throw std::runtime_error("invalid keypoint blob for image " +
                               std::to_string(image_id));
    }
    row.values.resize(expected / sizeof(float));
    std::memcpy(row.values.data(), blob, expected);
    keypoints.emplace(image_id, std::move(row));
  }
  sqlite3_finalize(statement);
  return keypoints;
}

std::vector<GeometryRow> ReadGeometries(sqlite3* db) {
  sqlite3_stmt* statement = nullptr;
  CheckSqlite(sqlite3_prepare_v2(
                  db,
                  "SELECT pair_id, rows, cols, data FROM "
                  "two_view_geometries WHERE rows > 0 ORDER BY pair_id",
                  -1, &statement, nullptr),
              db, "prepare two-view geometries");
  std::vector<GeometryRow> rows;
  while (sqlite3_step(statement) == SQLITE_ROW) {
    const int64_t pair_id = sqlite3_column_int64(statement, 0);
    const int count = sqlite3_column_int(statement, 1);
    const int cols = sqlite3_column_int(statement, 2);
    const void* blob = sqlite3_column_blob(statement, 3);
    const int bytes = sqlite3_column_bytes(statement, 3);
    if (cols != 2 || blob == nullptr ||
        bytes != count * cols * static_cast<int>(sizeof(uint32_t))) {
      sqlite3_finalize(statement);
      throw std::runtime_error("invalid two-view geometry blob");
    }
    GeometryRow row;
    row.image_id1 = static_cast<int>(pair_id / kMaxImageId);
    row.image_id2 = static_cast<int>(pair_id % kMaxImageId);
    const uint32_t* matches = static_cast<const uint32_t*>(blob);
    row.matches.reserve(count);
    for (int i = 0; i < count; ++i) {
      row.matches.emplace_back(matches[2 * i], matches[2 * i + 1]);
    }
    rows.push_back(std::move(row));
  }
  sqlite3_finalize(statement);
  return rows;
}

uint64_t FeatureKey(const int image_id, const uint32_t feature_id) {
  return (static_cast<uint64_t>(static_cast<uint32_t>(image_id)) << 32) |
         feature_id;
}

double Median(std::vector<double> values) {
  if (values.empty()) return std::numeric_limits<double>::quiet_NaN();
  const size_t middle = values.size() / 2;
  std::nth_element(values.begin(), values.begin() + middle, values.end());
  const double high = values[middle];
  if (values.size() % 2 == 1) return high;
  std::nth_element(values.begin(), values.begin() + middle - 1,
                   values.begin() + middle);
  return 0.5 * (values[middle - 1] + high);
}

void UpdateKeypoints(sqlite3* db,
                     const std::unordered_map<int, Keypoints>& keypoints) {
  CheckSqlite(sqlite3_exec(db, "BEGIN IMMEDIATE", nullptr, nullptr, nullptr),
              db, "begin keypoint update");
  sqlite3_stmt* statement = nullptr;
  try {
    CheckSqlite(sqlite3_prepare_v2(
                    db, "UPDATE keypoints SET data = ? WHERE image_id = ?", -1,
                    &statement, nullptr),
                db, "prepare keypoint update");
    for (const auto& [image_id, row] : keypoints) {
      CheckSqlite(sqlite3_bind_blob(
                      statement, 1, row.values.data(),
                      static_cast<int>(row.values.size() * sizeof(float)),
                      SQLITE_TRANSIENT),
                  db, "bind keypoints");
      CheckSqlite(sqlite3_bind_int(statement, 2, image_id), db,
                  "bind image id");
      CheckSqlite(sqlite3_step(statement), db, "update keypoints");
      sqlite3_reset(statement);
      sqlite3_clear_bindings(statement);
    }
    sqlite3_finalize(statement);
    statement = nullptr;
    CheckSqlite(sqlite3_exec(db, "COMMIT", nullptr, nullptr, nullptr), db,
                "commit keypoint update");
  } catch (...) {
    if (statement) sqlite3_finalize(statement);
    sqlite3_exec(db, "ROLLBACK", nullptr, nullptr, nullptr);
    throw;
  }
}

double ParseDoubleArg(const std::string& arg, const char* prefix,
                      const double fallback) {
  const std::string key(prefix);
  if (arg.rfind(key, 0) != 0) return fallback;
  return std::stod(arg.substr(key.size()));
}

int ParseIntArg(const std::string& arg, const char* prefix,
                const int fallback) {
  const std::string key(prefix);
  if (arg.rfind(key, 0) != 0) return fallback;
  return std::stoi(arg.substr(key.size()));
}

int SelfTest() {
  constexpr int width = 96;
  constexpr int height = 80;
  const double shift_x = 1.2;
  const double shift_y = -0.8;
  const auto texture = [](const double x, const double y) {
    return 128.0 + 36.0 * std::sin(0.17 * x) + 31.0 * std::cos(0.13 * y) +
           24.0 * std::sin(0.11 * (x + y));
  };
  std::vector<uint8_t> source(width * height);
  std::vector<uint8_t> target(width * height);
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      source[y * width + x] = static_cast<uint8_t>(std::clamp(
          std::lround(texture(x, y)), 0L, 255L));
      target[y * width + x] = static_cast<uint8_t>(std::clamp(
          std::lround(texture(x - shift_x, y - shift_y)), 0L, 255L));
    }
  }
  const aether_patch::GrayImageView source_view{source.data(), width, height,
                                                 width};
  const aether_patch::GrayImageView target_view{target.data(), width, height,
                                                 width};
  Image source_image;
  source_image.width = width;
  source_image.height = height;
  source_image.gray = source;
  source_image.BuildPyramid(2);
  Image target_image;
  target_image.width = width;
  target_image.height = height;
  target_image.gray = target;
  target_image.BuildPyramid(2);
  const double source_x = 47.3;
  const double source_y = 39.7;
  const double initial_x = source_x + shift_x + 0.55;
  const double initial_y = source_y + shift_y - 0.45;
  const auto result = aether_patch::AlignPyramidalTranslation(
      source_image.pyramid_views, source_x, source_y,
      target_image.pyramid_views, initial_x, initial_y);
  const double endpoint_error =
      std::hypot(result.x - (source_x + shift_x),
                 result.y - (source_y + shift_y));
  std::cout << "{\"ok\":" << (result.ok ? "true" : "false")
            << ",\"endpoint_error_px\":" << endpoint_error
            << ",\"estimated_shift_from_initial_px\":" << result.shift_px
            << ",\"photometric_error\":" << result.zero_mean_abs_error
            << "}\n";
  return result.ok && endpoint_error <= 0.15 ? 0 : 1;
}

int Run(const std::filesystem::path& input_db,
        const std::filesystem::path& ledger,
        const std::filesystem::path& gray_dir,
        const std::filesystem::path& output_db,
        const std::filesystem::path& stats_path, const Options& options) {
  if (std::filesystem::exists(stats_path)) {
    throw std::runtime_error("refusing to overwrite " + stats_path.string());
  }
  const auto start = Clock::now();
  BackupDatabase(input_db, output_db);
  sqlite3* db = nullptr;
  CheckSqlite(sqlite3_open_v2(output_db.string().c_str(), &db,
                              SQLITE_OPEN_READWRITE, nullptr),
              db, "open output database");
  try {
    const auto gray_paths = ReadGrayPaths(ledger, gray_dir);
    size_t gray_bytes = 0;
    auto images =
        ReadImages(db, gray_paths, options.pyramid_levels, &gray_bytes);
    auto keypoints = ReadKeypoints(db);
    sqlite3* geometry_db = db;
    if (!options.geometry_db.empty()) {
      CheckSqlite(OpenImmutable(options.geometry_db, &geometry_db),
                  geometry_db, "open geometry database");
    }
    const auto geometries = ReadGeometries(geometry_db);
    if (geometry_db != db) sqlite3_close(geometry_db);

    std::unordered_map<uint64_t, std::vector<Proposal>> proposals;
    int64_t attempted_edges = 0;
    int64_t accepted_edges = 0;
    for (const GeometryRow& geometry : geometries) {
      const auto image1 = images.find(geometry.image_id1);
      const auto image2 = images.find(geometry.image_id2);
      const auto keypoints1 = keypoints.find(geometry.image_id1);
      const auto keypoints2 = keypoints.find(geometry.image_id2);
      if (image1 == images.end() || image2 == images.end() ||
          keypoints1 == keypoints.end() || keypoints2 == keypoints.end()) {
        throw std::runtime_error("geometry references missing image");
      }
      for (const auto [feature1, feature2] : geometry.matches) {
        ++attempted_edges;
        if (feature1 >= static_cast<uint32_t>(keypoints1->second.rows) ||
            feature2 >= static_cast<uint32_t>(keypoints2->second.rows)) {
          throw std::runtime_error("geometry references missing keypoint");
        }
        const float* point1 = keypoints1->second.values.data() +
                              feature1 * keypoints1->second.cols;
        const float* point2 = keypoints2->second.values.data() +
                              feature2 * keypoints2->second.cols;
        const auto refined2 = aether_patch::AlignPyramidalTranslation(
            image1->second.pyramid_views, point1[0], point1[1],
            image2->second.pyramid_views, point2[0], point2[1],
            options.align);
        const auto refined1 = aether_patch::AlignPyramidalTranslation(
            image2->second.pyramid_views, point2[0], point2[1],
            image1->second.pyramid_views, point1[0], point1[1],
            options.align);
        if (!refined1.ok || !refined2.ok) continue;
        ++accepted_edges;
        proposals[FeatureKey(geometry.image_id1, feature1)].push_back(
            {refined1.x, refined1.y, refined1.zero_mean_abs_error,
             geometry.image_id2});
        proposals[FeatureKey(geometry.image_id2, feature2)].push_back(
            {refined2.x, refined2.y, refined2.zero_mean_abs_error,
             geometry.image_id1});
      }
    }

    int supported_keypoints = 0;
    int consensus_rejected = 0;
    int refined_keypoints = 0;
    std::vector<double> final_shifts;
    for (auto& [key, raw_values] : proposals) {
      std::sort(raw_values.begin(), raw_values.end(),
                [](const Proposal& lhs, const Proposal& rhs) {
                  if (lhs.support_image_id != rhs.support_image_id) {
                    return lhs.support_image_id < rhs.support_image_id;
                  }
                  return lhs.error < rhs.error;
                });
      std::vector<Proposal> values;
      for (const Proposal& proposal : raw_values) {
        if (!values.empty() && values.back().support_image_id ==
                                   proposal.support_image_id) {
          continue;
        }
        values.push_back(proposal);
      }
      if (static_cast<int>(values.size()) < options.min_support) continue;
      ++supported_keypoints;
      std::vector<double> xs;
      std::vector<double> ys;
      xs.reserve(values.size());
      ys.reserve(values.size());
      for (const Proposal& proposal : values) {
        xs.push_back(proposal.x);
        ys.push_back(proposal.y);
      }
      const double first_x = Median(xs);
      const double first_y = Median(ys);
      std::vector<double> consensus_x;
      std::vector<double> consensus_y;
      for (const Proposal& proposal : values) {
        if (std::hypot(proposal.x - first_x, proposal.y - first_y) <=
            options.consensus_radius_px) {
          consensus_x.push_back(proposal.x);
          consensus_y.push_back(proposal.y);
        }
      }
      if (static_cast<int>(consensus_x.size()) < options.min_support) {
        ++consensus_rejected;
        continue;
      }
      const int image_id = static_cast<int>(key >> 32);
      const uint32_t feature_id = static_cast<uint32_t>(key);
      Keypoints& row = keypoints.at(image_id);
      float* point = row.values.data() + feature_id * row.cols;
      const double final_x = Median(consensus_x);
      const double final_y = Median(consensus_y);
      const double shift = std::hypot(final_x - point[0], final_y - point[1]);
      if (shift > options.max_final_shift_px) {
        ++consensus_rejected;
        continue;
      }
      point[0] = static_cast<float>(final_x);
      point[1] = static_cast<float>(final_y);
      final_shifts.push_back(shift);
      ++refined_keypoints;
    }
    UpdateKeypoints(db, keypoints);
    sqlite3_close(db);
    db = nullptr;

    const double elapsed_ms = std::chrono::duration<double, std::milli>(
                                  Clock::now() - start)
                                  .count();
    const double median_shift = Median(final_shifts);
    std::ofstream stats(stats_path);
    if (!stats) throw std::runtime_error("cannot write " + stats_path.string());
    stats << "{\n"
          << "  \"schema\": \"pocketworld_cpp_multiview_patch_refine_v1\",\n"
          << "  \"input_db\": \"" << input_db.string() << "\",\n"
          << "  \"output_db\": \"" << output_db.string() << "\",\n"
          << "  \"geometry_db\": \""
          << (options.geometry_db.empty() ? input_db.string()
                                          : options.geometry_db.string())
          << "\",\n"
          << "  \"images\": " << images.size() << ",\n"
          << "  \"gray_bytes\": " << gray_bytes << ",\n"
          << "  \"verified_pairs\": " << geometries.size() << ",\n"
          << "  \"attempted_match_edges\": " << attempted_edges << ",\n"
          << "  \"accepted_symmetric_patch_edges\": " << accepted_edges
          << ",\n"
          << "  \"keypoints_with_min_view_support\": "
          << supported_keypoints << ",\n"
          << "  \"consensus_rejected_keypoints\": " << consensus_rejected
          << ",\n"
          << "  \"refined_keypoints\": " << refined_keypoints << ",\n"
          << "  \"final_shift_median_px\": "
          << (std::isfinite(median_shift) ? median_shift : 0.0) << ",\n"
          << "  \"elapsed_ms\": " << elapsed_ms << ",\n"
          << "  \"parameters\": {\n"
          << "    \"patch_radius\": " << options.align.patch_radius << ",\n"
          << "    \"pyramid_levels\": " << options.pyramid_levels << ",\n"
          << "    \"min_view_support\": " << options.min_support << ",\n"
          << "    \"consensus_radius_px\": "
          << options.consensus_radius_px << ",\n"
          << "    \"max_pair_shift_px\": " << options.align.max_shift_px
          << ",\n"
          << "    \"max_final_shift_px\": " << options.max_final_shift_px
          << ",\n"
          << "    \"max_zero_mean_abs_error\": "
          << options.align.max_zero_mean_abs_error << "\n"
          << "  },\n"
          << "  \"uses_lidar_or_scene_depth\": false,\n"
          << "  \"deletes_frames_matches_or_points\": false\n"
          << "}\n";
    stats.close();
    std::ifstream echo(stats_path);
    std::cout << echo.rdbuf();
    return 0;
  } catch (...) {
    if (db) sqlite3_close(db);
    throw;
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string(argv[1]) == "--self-test") return SelfTest();
    if (argc < 6) {
      std::fprintf(
          stderr,
          "usage: %s <input.db> <ledger.jsonl> <gray_dir> <output.db> "
          "<stats.json> [--min-support=N] [--consensus-radius=PX] "
          "[--pyramid-levels=N] "
          "[--max-pair-shift=PX] [--max-final-shift=PX] "
          "[--max-photometric-error=VALUE] [--patch-radius=N] "
          "[--geometry-db=PATH]\n",
          argv[0]);
      return 2;
    }
    Options options;
    for (int i = 6; i < argc; ++i) {
      const std::string arg(argv[i]);
      options.min_support =
          ParseIntArg(arg, "--min-support=", options.min_support);
      options.pyramid_levels =
          ParseIntArg(arg, "--pyramid-levels=", options.pyramid_levels);
      options.consensus_radius_px = ParseDoubleArg(
          arg, "--consensus-radius=", options.consensus_radius_px);
      options.align.max_shift_px = ParseDoubleArg(
          arg, "--max-pair-shift=", options.align.max_shift_px);
      options.max_final_shift_px = ParseDoubleArg(
          arg, "--max-final-shift=", options.max_final_shift_px);
      options.align.max_zero_mean_abs_error = ParseDoubleArg(
          arg, "--max-photometric-error=",
          options.align.max_zero_mean_abs_error);
      options.align.patch_radius =
          ParseIntArg(arg, "--patch-radius=", options.align.patch_radius);
      constexpr const char* kGeometryPrefix = "--geometry-db=";
      if (arg.rfind(kGeometryPrefix, 0) == 0) {
        options.geometry_db = arg.substr(std::strlen(kGeometryPrefix));
      }
    }
    if (options.pyramid_levels < 0 || options.pyramid_levels > 4) {
      throw std::runtime_error("--pyramid-levels must be between 0 and 4");
    }
    return Run(argv[1], argv[2], argv[3], argv[4], argv[5], options);
  } catch (const std::exception& error) {
    std::fprintf(stderr, "multiview_patch_refine: %s\n", error.what());
    return 1;
  }
}
