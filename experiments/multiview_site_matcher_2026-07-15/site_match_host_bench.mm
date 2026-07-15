#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

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
#include <limits>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

extern "C" int aether_gpu_match_gemm_pairs(
    const std::uint8_t* dA, int nA, const std::uint8_t* dB, int nB,
    double max_ratio, std::uint32_t* out_pairs, int max_pairs,
    int* out_num_matches);

namespace {

constexpr std::int64_t kMaxNumImages = 2147483647LL;
constexpr float kSqSiftNorm = 262144.0f;

[[noreturn]] void fail(const char* message) {
  std::fprintf(stderr, "FAIL: %s\n", message);
  std::exit(1);
}

struct FeatureTable {
  int rows = 0;
  std::vector<std::uint8_t> descriptors;
  std::vector<int> site_of_descriptor;
  std::vector<std::uint32_t> canonical_descriptor;
};

FeatureTable loadFeatures(sqlite3* db, int image_id) {
  sqlite3_stmt* statement = nullptr;
  const char* keypoint_sql =
      "SELECT rows, cols, data FROM keypoints WHERE image_id = ?";
  if (sqlite3_prepare_v2(db, keypoint_sql, -1, &statement, nullptr) !=
      SQLITE_OK) {
    fail(sqlite3_errmsg(db));
  }
  sqlite3_bind_int(statement, 1, image_id);
  if (sqlite3_step(statement) != SQLITE_ROW) fail("keypoints not found");
  FeatureTable table;
  table.rows = sqlite3_column_int(statement, 0);
  const int keypoint_cols = sqlite3_column_int(statement, 1);
  const auto* keypoint_data =
      static_cast<const float*>(sqlite3_column_blob(statement, 2));
  const int keypoint_bytes = sqlite3_column_bytes(statement, 2);
  if (table.rows <= 0 || keypoint_cols < 2 || keypoint_data == nullptr ||
      keypoint_bytes != table.rows * keypoint_cols * 4) {
    fail("invalid keypoint blob");
  }
  std::unordered_map<std::uint64_t, int> site_by_xy;
  table.site_of_descriptor.resize(table.rows);
  for (int index = 0; index < table.rows; ++index) {
    std::uint32_t x_bits = 0;
    std::uint32_t y_bits = 0;
    std::memcpy(&x_bits, keypoint_data + index * keypoint_cols, 4);
    std::memcpy(&y_bits, keypoint_data + index * keypoint_cols + 1, 4);
    const std::uint64_t key =
        (static_cast<std::uint64_t>(x_bits) << 32) | y_bits;
    auto [position, inserted] =
        site_by_xy.emplace(key, static_cast<int>(site_by_xy.size()));
    table.site_of_descriptor[index] = position->second;
    if (inserted) table.canonical_descriptor.push_back(index);
  }
  sqlite3_finalize(statement);

  const char* descriptor_sql =
      "SELECT rows, cols, data FROM descriptors WHERE image_id = ?";
  if (sqlite3_prepare_v2(db, descriptor_sql, -1, &statement, nullptr) !=
      SQLITE_OK) {
    fail(sqlite3_errmsg(db));
  }
  sqlite3_bind_int(statement, 1, image_id);
  if (sqlite3_step(statement) != SQLITE_ROW) fail("descriptors not found");
  const int descriptor_rows = sqlite3_column_int(statement, 0);
  const int descriptor_cols = sqlite3_column_int(statement, 1);
  const auto* descriptor_data = static_cast<const std::uint8_t*>(
      sqlite3_column_blob(statement, 2));
  const int descriptor_bytes = sqlite3_column_bytes(statement, 2);
  if (descriptor_rows != table.rows || descriptor_cols != 128 ||
      descriptor_data == nullptr || descriptor_bytes != table.rows * 128) {
    fail("invalid descriptor blob");
  }
  table.descriptors.assign(descriptor_data,
                           descriptor_data + descriptor_bytes);
  sqlite3_finalize(statement);
  return table;
}

std::vector<std::uint32_t> loadStoredPairs(sqlite3* db, int image_a,
                                           int image_b) {
  const int low = std::min(image_a, image_b);
  const int high = std::max(image_a, image_b);
  const std::int64_t pair_id =
      static_cast<std::int64_t>(low) * kMaxNumImages + high;
  sqlite3_stmt* statement = nullptr;
  if (sqlite3_prepare_v2(
          db, "SELECT rows, cols, data FROM matches WHERE pair_id = ?", -1,
          &statement, nullptr) != SQLITE_OK) {
    fail(sqlite3_errmsg(db));
  }
  sqlite3_bind_int64(statement, 1, pair_id);
  if (sqlite3_step(statement) != SQLITE_ROW) fail("match row not found");
  const int rows = sqlite3_column_int(statement, 0);
  const int cols = sqlite3_column_int(statement, 1);
  const auto* data = static_cast<const std::uint32_t*>(
      sqlite3_column_blob(statement, 2));
  const int bytes = sqlite3_column_bytes(statement, 2);
  if (rows < 0 || cols != 2 || bytes != rows * 8 ||
      (rows > 0 && data == nullptr)) {
    fail("invalid match blob");
  }
  std::vector<std::uint32_t> pairs(data, data + rows * 2);
  sqlite3_finalize(statement);
  if (image_a > image_b) {
    for (int row = 0; row < rows; ++row) {
      std::swap(pairs[2 * row], pairs[2 * row + 1]);
    }
  }
  return pairs;
}

const char* kSiteKernelSource = R"MSL(
#include <metal_stdlib>
#include <metal_simdgroup_matrix>
using namespace metal;

constant uint kD = 128u;
constant uint kKT = 16u;
constant uint kSG = 16u;
constant uint kMB = 128u;
constant uint kBN = 16u;

inline void update_distinct(float value, int site, int index,
                            thread float& best, thread int& bestSite,
                            thread int& bestIndex, thread float& second,
                            thread int& secondSite, thread int& secondIndex) {
  if (site < 0 || index < 0) return;
  if (site == bestSite) {
    if (value > best) { best = value; bestIndex = index; }
    return;
  }
  if (site == secondSite) {
    if (value > second) { second = value; secondIndex = index; }
    if (second > best) {
      const float oldBest = best; best = second; second = oldBest;
      const int oldBestSite = bestSite; bestSite = secondSite; secondSite = oldBestSite;
      const int oldBestIndex = bestIndex; bestIndex = secondIndex; secondIndex = oldBestIndex;
    }
    return;
  }
  if (value > best) {
    second = best; secondSite = bestSite; secondIndex = bestIndex;
    best = value; bestSite = site; bestIndex = index;
  } else if (value > second) {
    second = value; secondSite = site; secondIndex = index;
  }
}

kernel void pw_site_top2(device const half* A [[buffer(0)]],
                         device const half* B [[buffer(1)]],
                         device const int* sitesB [[buffer(2)]],
                         device int* outBestIndex [[buffer(3)]],
                         device int* outSecondIndex [[buffer(4)]],
                         device float* outBestDot [[buffer(5)]],
                         device float* outSecondDot [[buffer(6)]],
                         constant uint& numA [[buffer(7)]],
                         constant uint& numB [[buffer(8)]],
                         threadgroup half* Bsh [[threadgroup(0)]],
                         threadgroup float* acc [[threadgroup(1)]],
                         uint tgid [[threadgroup_position_in_grid]],
                         uint lid [[thread_index_in_threadgroup]],
                         uint sgid [[simdgroup_index_in_threadgroup]]) {
  const uint row0 = tgid * kMB;
  if (row0 >= numA) return;
  const uint rows = min(kMB, numA - row0);
  const uint aRow0 = row0 + sgid * 8u;
  simdgroup_matrix<half, 8, 8> aFrag[kKT];
  for (uint k = 0; k < kKT; ++k) {
    simdgroup_load(aFrag[k], A + aRow0 * kD + k * 8u, kD, ulong2(0, 0));
  }

  threadgroup float bestT[kMB];
  threadgroup float secondT[kMB];
  threadgroup int bestSiteT[kMB];
  threadgroup int secondSiteT[kMB];
  threadgroup int bestIndexT[kMB];
  threadgroup int secondIndexT[kMB];
  if (lid < kMB) {
    bestT[lid] = 0.0f; secondT[lid] = 0.0f;
    bestSiteT[lid] = -1; secondSiteT[lid] = -1;
    bestIndexT[lid] = -1; secondIndexT[lid] = -1;
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);

  for (uint col0 = 0; col0 < numB; col0 += kBN) {
    const uint cols = min(kBN, numB - col0);
    for (uint e = lid; e < kBN * kD; e += 512u) {
      const uint row = e / kD;
      const uint dim = e % kD;
      Bsh[e] = row < cols ? B[(col0 + row) * kD + dim] : half(0);
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    for (uint tile = 0; tile < 2u; ++tile) {
      simdgroup_matrix<float, 8, 8> c =
          make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      for (uint k = 0; k < kKT; ++k) {
        simdgroup_matrix<half, 8, 8> bFrag;
        simdgroup_load(bFrag, Bsh + tile * 8u * kD + k * 8u, kD,
                       ulong2(0, 0), true);
        simdgroup_multiply_accumulate(c, aFrag[k], bFrag, c);
      }
      simdgroup_store(c, acc + sgid * 8u * kBN + tile * 8u, kBN,
                      ulong2(0, 0));
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if (lid < rows) {
      float best = bestT[lid], second = secondT[lid];
      int bestSite = bestSiteT[lid], secondSite = secondSiteT[lid];
      int bestIndex = bestIndexT[lid], secondIndex = secondIndexT[lid];
      for (uint column = 0; column < cols; ++column) {
        const int index = int(col0 + column);
        update_distinct(acc[lid * kBN + column], sitesB[index], index,
                        best, bestSite, bestIndex,
                        second, secondSite, secondIndex);
      }
      bestT[lid] = best; secondT[lid] = second;
      bestSiteT[lid] = bestSite; secondSiteT[lid] = secondSite;
      bestIndexT[lid] = bestIndex; secondIndexT[lid] = secondIndex;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
  }
  if (lid < rows) {
    outBestIndex[row0 + lid] = bestIndexT[lid];
    outSecondIndex[row0 + lid] = secondIndexT[lid];
    outBestDot[row0 + lid] = bestT[lid];
    outSecondDot[row0 + lid] = secondT[lid];
  }
}
)MSL";

struct OneWayTop2 {
  std::vector<int> best_index;
  std::vector<int> second_index;
  std::vector<float> best_dot;
  std::vector<float> second_dot;
};

OneWayTop2 runOneWay(id<MTLDevice> device, id<MTLCommandQueue> queue,
                     id<MTLComputePipelineState> pipeline,
                     const FeatureTable& query, const FeatureTable& database) {
  const int dimension = 128;
  const NSUInteger query_padded = (query.rows + 127) / 128 * 128;
  const NSUInteger database_padded = (database.rows + 127) / 128 * 128;
  id<MTLBuffer> query_buffer =
      [device newBufferWithLength:query_padded * dimension * sizeof(__fp16)
                          options:MTLResourceStorageModeShared];
  id<MTLBuffer> database_buffer =
      [device newBufferWithLength:database_padded * dimension * sizeof(__fp16)
                          options:MTLResourceStorageModeShared];
  auto* query_half = static_cast<__fp16*>(query_buffer.contents);
  auto* database_half = static_cast<__fp16*>(database_buffer.contents);
  for (int index = 0; index < query.rows * dimension; ++index) {
    query_half[index] = query.descriptors[index];
  }
  for (NSUInteger index = query.rows * dimension;
       index < query_padded * dimension; ++index) {
    query_half[index] = 0;
  }
  for (int index = 0; index < database.rows * dimension; ++index) {
    database_half[index] = database.descriptors[index];
  }
  for (NSUInteger index = database.rows * dimension;
       index < database_padded * dimension; ++index) {
    database_half[index] = 0;
  }
  id<MTLBuffer> sites =
      [device newBufferWithBytes:database.site_of_descriptor.data()
                          length:database.rows * sizeof(int)
                         options:MTLResourceStorageModeShared];
  id<MTLBuffer> best_index =
      [device newBufferWithLength:query.rows * sizeof(int)
                          options:MTLResourceStorageModeShared];
  id<MTLBuffer> second_index =
      [device newBufferWithLength:query.rows * sizeof(int)
                          options:MTLResourceStorageModeShared];
  id<MTLBuffer> best_dot =
      [device newBufferWithLength:query.rows * sizeof(float)
                          options:MTLResourceStorageModeShared];
  id<MTLBuffer> second_dot =
      [device newBufferWithLength:query.rows * sizeof(float)
                          options:MTLResourceStorageModeShared];
  if (!query_buffer || !database_buffer || !sites || !best_index ||
      !second_index || !best_dot || !second_dot) {
    fail("Metal buffer allocation failed");
  }
  id<MTLCommandBuffer> command = [queue commandBuffer];
  id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
  [encoder setComputePipelineState:pipeline];
  [encoder setBuffer:query_buffer offset:0 atIndex:0];
  [encoder setBuffer:database_buffer offset:0 atIndex:1];
  [encoder setBuffer:sites offset:0 atIndex:2];
  [encoder setBuffer:best_index offset:0 atIndex:3];
  [encoder setBuffer:second_index offset:0 atIndex:4];
  [encoder setBuffer:best_dot offset:0 atIndex:5];
  [encoder setBuffer:second_dot offset:0 atIndex:6];
  std::uint32_t num_query = query.rows;
  std::uint32_t num_database = database.rows;
  [encoder setBytes:&num_query length:4 atIndex:7];
  [encoder setBytes:&num_database length:4 atIndex:8];
  [encoder setThreadgroupMemoryLength:16 * 128 * sizeof(__fp16) atIndex:0];
  [encoder setThreadgroupMemoryLength:128 * 16 * sizeof(float) atIndex:1];
  [encoder dispatchThreadgroups:MTLSizeMake((query.rows + 127) / 128, 1, 1)
             threadsPerThreadgroup:MTLSizeMake(512, 1, 1)];
  [encoder endEncoding];
  [command commit];
  [command waitUntilCompleted];
  if (command.status == MTLCommandBufferStatusError) {
    fail(command.error.localizedDescription.UTF8String);
  }
  OneWayTop2 output;
  output.best_index.assign(static_cast<int*>(best_index.contents),
                           static_cast<int*>(best_index.contents) + query.rows);
  output.second_index.assign(
      static_cast<int*>(second_index.contents),
      static_cast<int*>(second_index.contents) + query.rows);
  output.best_dot.assign(static_cast<float*>(best_dot.contents),
                         static_cast<float*>(best_dot.contents) + query.rows);
  output.second_dot.assign(
      static_cast<float*>(second_dot.contents),
      static_cast<float*>(second_dot.contents) + query.rows);
  return output;
}

struct Candidate {
  float dot = 0.0f;
  int database_site = -1;
};

void updateCandidate(Candidate& best, Candidate& second, float dot,
                     int database_site) {
  if (database_site < 0) return;
  if (database_site == best.database_site) {
    if (dot > best.dot) best.dot = dot;
    return;
  }
  if (database_site == second.database_site) {
    if (dot > second.dot) second.dot = dot;
    if (second.dot > best.dot) std::swap(best, second);
    return;
  }
  if (dot > best.dot) {
    second = best;
    best = {dot, database_site};
  } else if (dot > second.dot) {
    second = {dot, database_site};
  }
}

std::vector<int> reduceToSiteMatches(const FeatureTable& query,
                                     const FeatureTable& database,
                                     const OneWayTop2& descriptor_top2,
                                     float max_ratio) {
  std::vector<Candidate> best(query.canonical_descriptor.size());
  std::vector<Candidate> second(query.canonical_descriptor.size());
  for (int descriptor = 0; descriptor < query.rows; ++descriptor) {
    const int query_site = query.site_of_descriptor[descriptor];
    for (const auto [index, dot] : {
             std::pair{descriptor_top2.best_index[descriptor],
                       descriptor_top2.best_dot[descriptor]},
             std::pair{descriptor_top2.second_index[descriptor],
                       descriptor_top2.second_dot[descriptor]}}) {
      if (index < 0 || index >= database.rows) continue;
      updateCandidate(best[query_site], second[query_site], dot,
                      database.site_of_descriptor[index]);
    }
  }
  std::vector<int> result(query.canonical_descriptor.size(), -1);
  for (std::size_t site = 0; site < result.size(); ++site) {
    if (best[site].database_site < 0) continue;
    const float best_distance =
        std::acos(std::min(best[site].dot / kSqSiftNorm, 1.0f));
    const float second_distance =
        std::acos(std::min(second[site].dot / kSqSiftNorm, 1.0f));
    if (best_distance <= 0.7f && best_distance < max_ratio * second_distance) {
      result[site] = best[site].database_site;
    }
  }
  return result;
}

std::vector<std::uint32_t> siteMutualPairs(const FeatureTable& a,
                                           const FeatureTable& b,
                                           const OneWayTop2& ab_top2,
                                           const OneWayTop2& ba_top2) {
  const auto ab = reduceToSiteMatches(a, b, ab_top2, 0.7f);
  const auto ba = reduceToSiteMatches(b, a, ba_top2, 0.7f);
  std::vector<std::uint32_t> pairs;
  for (std::size_t site_a = 0; site_a < ab.size(); ++site_a) {
    const int site_b = ab[site_a];
    if (site_b >= 0 && site_b < static_cast<int>(ba.size()) &&
        ba[site_b] == static_cast<int>(site_a)) {
      pairs.push_back(a.canonical_descriptor[site_a]);
      pairs.push_back(b.canonical_descriptor[site_b]);
    }
  }
  return pairs;
}

std::uint64_t key(std::uint32_t first, std::uint32_t second) {
  return (static_cast<std::uint64_t>(first) << 32) | second;
}

std::unordered_set<std::uint64_t> canonicalSet(
    const std::vector<std::uint32_t>& pairs, const FeatureTable& a,
    const FeatureTable& b) {
  std::unordered_set<std::uint64_t> result;
  for (std::size_t row = 0; row + 1 < pairs.size(); row += 2) {
    const int site_a = a.site_of_descriptor.at(pairs[row]);
    const int site_b = b.site_of_descriptor.at(pairs[row + 1]);
    result.insert(key(a.canonical_descriptor[site_a],
                      b.canonical_descriptor[site_b]));
  }
  return result;
}

void execute(sqlite3* database, const char* sql) {
  char* error = nullptr;
  if (sqlite3_exec(database, sql, nullptr, nullptr, &error) != SQLITE_OK) {
    const std::string message = error ? error : sqlite3_errmsg(database);
    sqlite3_free(error);
    fail(message.c_str());
  }
}

void updatePairBlob(sqlite3* database, const char* table,
                    std::int64_t pair_id,
                    const std::vector<std::uint32_t>& pairs) {
  const std::string sql = std::string("UPDATE ") + table +
      " SET rows = ?, cols = 2, data = ? WHERE pair_id = ?";
  sqlite3_stmt* statement = nullptr;
  if (sqlite3_prepare_v2(database, sql.c_str(), -1, &statement, nullptr) !=
      SQLITE_OK) {
    fail(sqlite3_errmsg(database));
  }
  sqlite3_bind_int(statement, 1, static_cast<int>(pairs.size() / 2));
  sqlite3_bind_blob(statement, 2, pairs.data(),
                    static_cast<int>(pairs.size() * sizeof(std::uint32_t)),
                    SQLITE_TRANSIENT);
  sqlite3_bind_int64(statement, 3, pair_id);
  if (sqlite3_step(statement) != SQLITE_DONE) fail(sqlite3_errmsg(database));
  sqlite3_finalize(statement);
}

void deletePairRow(sqlite3* database, const char* table,
                   std::int64_t pair_id) {
  const std::string sql =
      std::string("DELETE FROM ") + table + " WHERE pair_id = ?";
  sqlite3_stmt* statement = nullptr;
  if (sqlite3_prepare_v2(database, sql.c_str(), -1, &statement, nullptr) !=
      SQLITE_OK) {
    fail(sqlite3_errmsg(database));
  }
  sqlite3_bind_int64(statement, 1, pair_id);
  if (sqlite3_step(statement) != SQLITE_DONE) fail(sqlite3_errmsg(database));
  sqlite3_finalize(statement);
}

bool pairRowExists(sqlite3* database, const char* table,
                   std::int64_t pair_id) {
  const std::string sql =
      std::string("SELECT 1 FROM ") + table + " WHERE pair_id = ?";
  sqlite3_stmt* statement = nullptr;
  if (sqlite3_prepare_v2(database, sql.c_str(), -1, &statement, nullptr) !=
      SQLITE_OK) {
    fail(sqlite3_errmsg(database));
  }
  sqlite3_bind_int64(statement, 1, pair_id);
  const bool exists = sqlite3_step(statement) == SQLITE_ROW;
  sqlite3_finalize(statement);
  return exists;
}

void insertPairBlob(sqlite3* database, const char* table,
                    std::int64_t pair_id,
                    const std::vector<std::uint32_t>& pairs) {
  const std::string sql = std::string("INSERT INTO ") + table +
      "(pair_id, rows, cols, data) VALUES (?, ?, 2, ?)";
  sqlite3_stmt* statement = nullptr;
  if (sqlite3_prepare_v2(database, sql.c_str(), -1, &statement, nullptr) !=
      SQLITE_OK) {
    fail(sqlite3_errmsg(database));
  }
  sqlite3_bind_int64(statement, 1, pair_id);
  sqlite3_bind_int(statement, 2, static_cast<int>(pairs.size() / 2));
  sqlite3_bind_blob(statement, 3, pairs.data(),
                    static_cast<int>(pairs.size() * sizeof(std::uint32_t)),
                    SQLITE_TRANSIENT);
  if (sqlite3_step(statement) != SQLITE_DONE) fail(sqlite3_errmsg(database));
  sqlite3_finalize(statement);
}

std::vector<std::uint32_t> loadPairBlob(sqlite3* database, const char* table,
                                        std::int64_t pair_id) {
  const std::string sql = std::string("SELECT rows, cols, data FROM ") +
                          table + " WHERE pair_id = ?";
  sqlite3_stmt* statement = nullptr;
  if (sqlite3_prepare_v2(database, sql.c_str(), -1, &statement, nullptr) !=
      SQLITE_OK) {
    fail(sqlite3_errmsg(database));
  }
  sqlite3_bind_int64(statement, 1, pair_id);
  if (sqlite3_step(statement) != SQLITE_ROW) {
    sqlite3_finalize(statement);
    return {};
  }
  const int rows = sqlite3_column_int(statement, 0);
  const int cols = sqlite3_column_int(statement, 1);
  const auto* data = static_cast<const std::uint32_t*>(
      sqlite3_column_blob(statement, 2));
  const int bytes = sqlite3_column_bytes(statement, 2);
  if (rows < 0 || cols != 2 || bytes != rows * 8 ||
      (rows > 0 && data == nullptr)) {
    fail("invalid pair blob");
  }
  std::vector<std::uint32_t> pairs(data, data + rows * 2);
  sqlite3_finalize(statement);
  return pairs;
}

std::vector<std::uint32_t> canonicalizedIntersection(
    const std::vector<std::uint32_t>& source,
    const std::unordered_set<std::uint64_t>& allowed,
    const FeatureTable& a, const FeatureTable& b) {
  std::vector<std::uint32_t> output;
  std::unordered_set<std::uint64_t> seen;
  for (std::size_t row = 0; row + 1 < source.size(); row += 2) {
    if (source[row] >= static_cast<std::uint32_t>(a.rows) ||
        source[row + 1] >= static_cast<std::uint32_t>(b.rows)) {
      fail("pair endpoint exceeds feature table");
    }
    const int site_a = a.site_of_descriptor[source[row]];
    const int site_b = b.site_of_descriptor[source[row + 1]];
    const std::uint32_t canonical_a = a.canonical_descriptor[site_a];
    const std::uint32_t canonical_b = b.canonical_descriptor[site_b];
    const std::uint64_t pair_key = key(canonical_a, canonical_b);
    if (!allowed.contains(pair_key) || !seen.insert(pair_key).second) continue;
    output.push_back(canonical_a);
    output.push_back(canonical_b);
  }
  return output;
}

int rewriteDatabase(const char* input_path, const char* output_path,
                    const char* stats_path, id<MTLDevice> device,
                    id<MTLCommandQueue> queue,
                    id<MTLComputePipelineState> pipeline) {
  if (std::filesystem::exists(output_path)) {
    fail("refusing to overwrite output database");
  }
  sqlite3* source = nullptr;
  sqlite3* output = nullptr;
  if (sqlite3_open_v2(input_path, &source, SQLITE_OPEN_READONLY, nullptr) !=
      SQLITE_OK) {
    fail(source ? sqlite3_errmsg(source) : "source open failed");
  }
  if (sqlite3_open(output_path, &output) != SQLITE_OK) {
    fail(output ? sqlite3_errmsg(output) : "output open failed");
  }
  sqlite3_backup* backup = sqlite3_backup_init(output, "main", source, "main");
  if (!backup) fail(sqlite3_errmsg(output));
  if (sqlite3_backup_step(backup, -1) != SQLITE_DONE) fail(sqlite3_errmsg(output));
  sqlite3_backup_finish(backup);
  sqlite3_close(source);

  std::unordered_map<int, FeatureTable> features;
  sqlite3_stmt* statement = nullptr;
  if (sqlite3_prepare_v2(output,
                         "SELECT image_id FROM descriptors ORDER BY image_id",
                         -1, &statement, nullptr) != SQLITE_OK) {
    fail(sqlite3_errmsg(output));
  }
  while (sqlite3_step(statement) == SQLITE_ROW) {
    const int image_id = sqlite3_column_int(statement, 0);
    features.emplace(image_id, loadFeatures(output, image_id));
  }
  sqlite3_finalize(statement);

  std::vector<std::int64_t> pair_ids;
  if (sqlite3_prepare_v2(output, "SELECT pair_id FROM matches ORDER BY pair_id",
                         -1, &statement, nullptr) != SQLITE_OK) {
    fail(sqlite3_errmsg(output));
  }
  while (sqlite3_step(statement) == SQLITE_ROW) {
    pair_ids.push_back(sqlite3_column_int64(statement, 0));
  }
  sqlite3_finalize(statement);

  std::uint64_t matches_before = 0;
  std::uint64_t matches_after = 0;
  std::uint64_t inliers_before = 0;
  std::uint64_t inliers_after = 0;
  std::uint64_t recovered = 0;
  std::uint64_t lost = 0;
  std::uint64_t match_pairs_written = 0;
  std::uint64_t geometry_pairs_written = 0;
  const auto start = std::chrono::steady_clock::now();
  execute(output, "BEGIN IMMEDIATE");
  for (std::size_t pair_index = 0; pair_index < pair_ids.size(); ++pair_index) {
    @autoreleasepool {
      const std::int64_t pair_id = pair_ids[pair_index];
      const int image_a = static_cast<int>(pair_id / kMaxNumImages);
      const int image_b = static_cast<int>(pair_id % kMaxNumImages);
      const auto feature_a = features.find(image_a);
      const auto feature_b = features.find(image_b);
      if (feature_a == features.end() || feature_b == features.end()) {
        fail("match pair references missing features");
      }
      const auto stored = loadPairBlob(output, "matches", pair_id);
      const auto ab_top2 = runOneWay(device, queue, pipeline, feature_a->second,
                                     feature_b->second);
      const auto ba_top2 = runOneWay(device, queue, pipeline, feature_b->second,
                                     feature_a->second);
      const auto site_pairs = siteMutualPairs(
          feature_a->second, feature_b->second, ab_top2, ba_top2);
      const auto old_sites =
          canonicalSet(stored, feature_a->second, feature_b->second);
      const auto new_sites =
          canonicalSet(site_pairs, feature_a->second, feature_b->second);
      for (const auto pair : new_sites) recovered += !old_sites.contains(pair);
      for (const auto pair : old_sites) lost += !new_sites.contains(pair);
      matches_before += stored.size() / 2;
      matches_after += site_pairs.size() / 2;
      if (site_pairs.empty()) {
        deletePairRow(output, "matches", pair_id);
      } else {
        updatePairBlob(output, "matches", pair_id, site_pairs);
        ++match_pairs_written;
      }

      const auto inliers = loadPairBlob(output, "two_view_geometries", pair_id);
      const auto retained = canonicalizedIntersection(
          inliers, new_sites, feature_a->second, feature_b->second);
      inliers_before += inliers.size() / 2;
      inliers_after += retained.size() / 2;
      if (retained.empty()) {
        deletePairRow(output, "two_view_geometries", pair_id);
      } else {
        updatePairBlob(output, "two_view_geometries", pair_id, retained);
        ++geometry_pairs_written;
      }
    }
    if ((pair_index + 1) % 100 == 0 || pair_index + 1 == pair_ids.size()) {
      std::fprintf(stderr, "site matcher %zu/%zu pairs\n", pair_index + 1,
                   pair_ids.size());
    }
  }
  execute(output, "COMMIT");
  execute(output, "PRAGMA wal_checkpoint(TRUNCATE)");
  sqlite3_close(output);
  const auto stop = std::chrono::steady_clock::now();
  const double elapsed_seconds =
      std::chrono::duration<double>(stop - start).count();
  std::ofstream stats(stats_path);
  if (!stats) fail("cannot create stats file");
  stats << "{\n"
        << "  \"schema\": \"pocketworld_exact_xy_site_matcher_v1\",\n"
        << "  \"input_db\": \"" << input_path << "\",\n"
        << "  \"output_db\": \"" << output_path << "\",\n"
        << "  \"images\": " << features.size() << ",\n"
        << "  \"pairs\": " << pair_ids.size() << ",\n"
        << "  \"match_pairs_written\": " << match_pairs_written << ",\n"
        << "  \"geometry_pairs_written\": " << geometry_pairs_written << ",\n"
        << "  \"matches_before\": " << matches_before << ",\n"
        << "  \"matches_after\": " << matches_after << ",\n"
        << "  \"site_pairs_recovered_vs_descriptor_matcher\": " << recovered
        << ",\n"
        << "  \"site_pairs_lost_vs_descriptor_matcher\": " << lost << ",\n"
        << "  \"two_view_inliers_before\": " << inliers_before << ",\n"
        << "  \"two_view_inliers_after\": " << inliers_after << ",\n"
        << "  \"elapsed_seconds\": " << elapsed_seconds << "\n"
        << "}\n";
  stats.close();
  std::printf(
      "{\"pairs\":%zu,\"match_pairs_written\":%llu,"
      "\"geometry_pairs_written\":%llu,\"matches_before\":%llu,"
      "\"matches_after\":%llu,"
      "\"recovered\":%llu,\"lost\":%llu,\"inliers_before\":%llu,"
      "\"inliers_after\":%llu,\"elapsed_seconds\":%.3f}\n",
      pair_ids.size(), static_cast<unsigned long long>(match_pairs_written),
      static_cast<unsigned long long>(geometry_pairs_written),
      static_cast<unsigned long long>(matches_before),
      static_cast<unsigned long long>(matches_after),
      static_cast<unsigned long long>(recovered),
      static_cast<unsigned long long>(lost),
      static_cast<unsigned long long>(inliers_before),
      static_cast<unsigned long long>(inliers_after), elapsed_seconds);
  return 0;
}

int augmentStarvedPairs(const char* input_path, const char* output_path,
                        const char* stats_path, int temporal_k,
                        int min_valid_pairs, int min_inliers) {
  if (temporal_k <= 0 || min_valid_pairs <= 0 || min_inliers <= 0) {
    fail("augment-starved thresholds must be positive");
  }
  if (std::filesystem::exists(output_path)) {
    fail("refusing to overwrite output database");
  }
  sqlite3* source = nullptr;
  sqlite3* output = nullptr;
  if (sqlite3_open_v2(input_path, &source, SQLITE_OPEN_READONLY, nullptr) !=
      SQLITE_OK) {
    fail(source ? sqlite3_errmsg(source) : "source open failed");
  }
  if (sqlite3_open(output_path, &output) != SQLITE_OK) {
    fail(output ? sqlite3_errmsg(output) : "output open failed");
  }
  sqlite3_backup* backup = sqlite3_backup_init(output, "main", source, "main");
  if (!backup) fail(sqlite3_errmsg(output));
  if (sqlite3_backup_step(backup, -1) != SQLITE_DONE) {
    fail(sqlite3_errmsg(source));
  }
  sqlite3_backup_finish(backup);
  sqlite3_close(source);

  std::vector<int> image_ids;
  sqlite3_stmt* statement = nullptr;
  if (sqlite3_prepare_v2(output,
                         "SELECT image_id FROM descriptors ORDER BY image_id",
                         -1, &statement, nullptr) != SQLITE_OK) {
    fail(sqlite3_errmsg(output));
  }
  while (sqlite3_step(statement) == SQLITE_ROW) {
    image_ids.push_back(sqlite3_column_int(statement, 0));
  }
  sqlite3_finalize(statement);
  std::unordered_map<int, int> index_of;
  for (int index = 0; index < static_cast<int>(image_ids.size()); ++index) {
    index_of[image_ids[index]] = index;
  }

  std::vector<int> valid_pairs(image_ids.size(), 0);
  if (sqlite3_prepare_v2(
          output, "SELECT pair_id, rows FROM two_view_geometries", -1,
          &statement, nullptr) != SQLITE_OK) {
    fail(sqlite3_errmsg(output));
  }
  while (sqlite3_step(statement) == SQLITE_ROW) {
    const std::int64_t pair_id = sqlite3_column_int64(statement, 0);
    const int rows = sqlite3_column_int(statement, 1);
    if (rows < min_inliers) continue;
    const int image_a = static_cast<int>(pair_id / kMaxNumImages);
    const int image_b = static_cast<int>(pair_id % kMaxNumImages);
    const auto a = index_of.find(image_a);
    const auto b = index_of.find(image_b);
    if (a == index_of.end() || b == index_of.end() ||
        std::abs(a->second - b->second) > temporal_k) {
      continue;
    }
    ++valid_pairs[a->second];
    ++valid_pairs[b->second];
  }
  sqlite3_finalize(statement);
  std::vector<char> starved(image_ids.size(), 0);
  int starved_count = 0;
  for (int index = 0; index < static_cast<int>(image_ids.size()); ++index) {
    if (valid_pairs[index] < min_valid_pairs) {
      starved[index] = 1;
      ++starved_count;
    }
  }

  std::vector<std::pair<int, int>> candidates;
  for (int gap = 1; gap <= temporal_k; ++gap) {
    for (int later = gap; later < static_cast<int>(image_ids.size()); ++later) {
      const int earlier = later - gap;
      if (gap > 2 && !starved[earlier] && !starved[later]) continue;
      const int low = std::min(image_ids[earlier], image_ids[later]);
      const int high = std::max(image_ids[earlier], image_ids[later]);
      const std::int64_t pair_id =
          static_cast<std::int64_t>(low) * kMaxNumImages + high;
      if (!pairRowExists(output, "matches", pair_id)) {
        candidates.emplace_back(earlier, later);
      }
    }
  }

  std::unordered_map<int, FeatureTable> features;
  features.reserve(image_ids.size());
  for (const int image_id : image_ids) {
    features.emplace(image_id, loadFeatures(output, image_id));
  }
  const auto start = std::chrono::steady_clock::now();
  std::uint64_t matches_written = 0;
  int pairs_written = 0;
  execute(output, "BEGIN IMMEDIATE");
  for (std::size_t index = 0; index < candidates.size(); ++index) {
    @autoreleasepool {
      const int earlier = candidates[index].first;
      const int later = candidates[index].second;
      const int image_a = image_ids[earlier];
      const int image_b = image_ids[later];
      const FeatureTable& a = features.at(image_a);
      const FeatureTable& b = features.at(image_b);
      const int capacity = std::min(a.rows, b.rows);
      std::vector<std::uint32_t> pairs(static_cast<std::size_t>(capacity) * 2);
      int num_matches = 0;
      const int rc = aether_gpu_match_gemm_pairs(
          a.descriptors.data(), a.rows, b.descriptors.data(), b.rows, 0.7,
          pairs.data(), capacity, &num_matches);
      if (rc != 0) fail("product Metal matcher failed during augmentation");
      pairs.resize(static_cast<std::size_t>(num_matches) * 2);
      if (!pairs.empty()) {
        const int low = std::min(image_a, image_b);
        const int high = std::max(image_a, image_b);
        if (image_a > image_b) {
          for (int row = 0; row < num_matches; ++row) {
            std::swap(pairs[2 * row], pairs[2 * row + 1]);
          }
        }
        const std::int64_t pair_id =
            static_cast<std::int64_t>(low) * kMaxNumImages + high;
        insertPairBlob(output, "matches", pair_id, pairs);
        ++pairs_written;
        matches_written += static_cast<std::uint64_t>(num_matches);
      }
    }
    if ((index + 1) % 25 == 0 || index + 1 == candidates.size()) {
      std::fprintf(stderr, "augment starved %zu/%zu pairs\n", index + 1,
                   candidates.size());
    }
  }
  execute(output, "COMMIT");
  execute(output, "PRAGMA wal_checkpoint(TRUNCATE)");
  sqlite3_close(output);
  const double elapsed_seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - start).count();

  std::ofstream stats(stats_path);
  if (!stats) fail("cannot create stats file");
  stats << "{\n"
        << "  \"schema\": \"pocketworld_metal_starved_pair_augmentation_v1\",\n"
        << "  \"input_db\": \"" << input_path << "\",\n"
        << "  \"output_db\": \"" << output_path << "\",\n"
        << "  \"images\": " << image_ids.size() << ",\n"
        << "  \"temporal_k\": " << temporal_k << ",\n"
        << "  \"min_valid_pairs\": " << min_valid_pairs << ",\n"
        << "  \"min_inliers\": " << min_inliers << ",\n"
        << "  \"starved_frames\": " << starved_count << ",\n"
        << "  \"candidate_pairs\": " << candidates.size() << ",\n"
        << "  \"pairs_written\": " << pairs_written << ",\n"
        << "  \"matches_written\": " << matches_written << ",\n"
        << "  \"elapsed_seconds\": " << elapsed_seconds << "\n"
        << "}\n";
  stats.close();
  std::printf(
      "{\"starved_frames\":%d,\"candidate_pairs\":%zu,"
      "\"pairs_written\":%d,\"matches_written\":%llu,"
      "\"elapsed_seconds\":%.3f}\n",
      starved_count, candidates.size(), pairs_written,
      static_cast<unsigned long long>(matches_written), elapsed_seconds);
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  @autoreleasepool {
    const bool rewrite_mode =
        argc == 5 && std::strcmp(argv[1], "--rewrite") == 0;
    const bool augment_mode =
        argc == 8 && std::strcmp(argv[1], "--augment-starved") == 0;
    if (!rewrite_mode && !augment_mode && argc != 4) {
      std::fprintf(
          stderr,
          "usage: %s <sfm_live.db> <image_a> <image_b>\n"
          "       %s --rewrite <input.db> <output.db> <stats.json>\n"
          "       %s --augment-starved <input.db> <output.db> <stats.json>"
          " <k> <min-valid-pairs> <min-inliers>\n",
          argv[0], argv[0], argv[0]);
      return 2;
    }

    if (augment_mode) {
      return augmentStarvedPairs(argv[2], argv[3], argv[4], std::atoi(argv[5]),
                                 std::atoi(argv[6]), std::atoi(argv[7]));
    }

    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    id<MTLCommandQueue> queue = [device newCommandQueue];
    NSError* error = nil;
    id<MTLLibrary> library =
        [device newLibraryWithSource:@(kSiteKernelSource) options:nil error:&error];
    if (!library) fail(error.localizedDescription.UTF8String);
    id<MTLFunction> function = [library newFunctionWithName:@"pw_site_top2"];
    id<MTLComputePipelineState> pipeline =
        [device newComputePipelineStateWithFunction:function error:&error];
    if (!pipeline) fail(error.localizedDescription.UTF8String);
    if (rewrite_mode) {
      return rewriteDatabase(argv[2], argv[3], argv[4], device, queue, pipeline);
    }

    sqlite3* database = nullptr;
    if (sqlite3_open_v2(argv[1], &database, SQLITE_OPEN_READONLY, nullptr) !=
        SQLITE_OK) {
      fail(database ? sqlite3_errmsg(database) : "sqlite open failed");
    }
    const int image_a = std::atoi(argv[2]);
    const int image_b = std::atoi(argv[3]);
    const FeatureTable a = loadFeatures(database, image_a);
    const FeatureTable b = loadFeatures(database, image_b);
    const auto stored = loadStoredPairs(database, image_a, image_b);
    sqlite3_close(database);

    const auto start = std::chrono::steady_clock::now();
    const auto ab_top2 = runOneWay(device, queue, pipeline, a, b);
    const auto ba_top2 = runOneWay(device, queue, pipeline, b, a);
    const auto site_pairs = siteMutualPairs(a, b, ab_top2, ba_top2);
    const auto stop = std::chrono::steady_clock::now();
    const double elapsed_ms =
        std::chrono::duration<double, std::milli>(stop - start).count();

    std::vector<std::uint32_t> product_pairs(
        static_cast<std::size_t>(std::min(a.rows, b.rows)) * 2);
    int product_count = 0;
    const int product_rc = aether_gpu_match_gemm_pairs(
        a.descriptors.data(), a.rows, b.descriptors.data(), b.rows, 0.7,
        product_pairs.data(), std::min(a.rows, b.rows), &product_count);
    product_pairs.resize(static_cast<std::size_t>(product_count) * 2);

    const auto stored_sites = canonicalSet(stored, a, b);
    const auto product_sites = canonicalSet(product_pairs, a, b);
    const auto new_sites = canonicalSet(site_pairs, a, b);
    std::size_t recovered = 0;
    std::size_t lost = 0;
    for (const auto pair : new_sites) recovered += !product_sites.contains(pair);
    for (const auto pair : product_sites) lost += !new_sites.contains(pair);
    std::printf(
        "{\"product_rc\":%d,\"image_a\":%d,\"image_b\":%d,"
        "\"descriptors_a\":%d,\"sites_a\":%zu,"
        "\"descriptors_b\":%d,\"sites_b\":%zu,"
        "\"stored_descriptor_matches\":%zu,\"stored_site_pairs\":%zu,"
        "\"product_descriptor_matches\":%d,\"product_site_pairs\":%zu,"
        "\"site_aware_matches\":%zu,\"recovered_vs_product\":%zu,"
        "\"lost_vs_product\":%zu,\"site_match_elapsed_ms\":%.3f}\n",
        product_rc, image_a, image_b, a.rows, a.canonical_descriptor.size(),
        b.rows, b.canonical_descriptor.size(), stored.size() / 2,
        stored_sites.size(), product_count, product_sites.size(),
        site_pairs.size() / 2, recovered, lost, elapsed_ms);
    return product_rc == 0 ? 0 : 1;
  }
}
