// fair_match_extract_fixture.cc — H2 harness step 0: freeze one immutable
// descriptor-pair fixture out of a capture database, read-only.
//
// usage: fair_match_extract_fixture <db_path> <out_dir> <image_a> <image_b>
//
// Opens the SQLite database with the immutable=1 URI flag so no WAL/SHM
// sidecar is created or touched. Writes out_dir/a.u8, out_dir/b.u8 and
// out_dir/manifest.json with SHA-256 of every artifact.

#include <sqlite3.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

#include "fair_match_common.h"

namespace {

struct Table {
  int rows = 0;
  std::vector<uint8_t> bytes;
};

Table ReadTable(sqlite3* db, long image_id) {
  sqlite3_stmt* stmt = nullptr;
  const char* sql =
      "SELECT rows, cols, data FROM descriptors WHERE image_id = ?";
  if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
    std::fprintf(stderr, "FAIL prepare: %s\n", sqlite3_errmsg(db));
    std::exit(2);
  }
  sqlite3_bind_int64(stmt, 1, image_id);
  Table t;
  if (sqlite3_step(stmt) != SQLITE_ROW) {
    std::fprintf(stderr, "FAIL image %ld has no descriptor row\n", image_id);
    std::exit(3);
  }
  t.rows = sqlite3_column_int(stmt, 0);
  const int cols = sqlite3_column_int(stmt, 1);
  const int nbytes = sqlite3_column_bytes(stmt, 2);
  const void* data = sqlite3_column_blob(stmt, 2);
  if (t.rows <= 0 || cols != 128 || nbytes != t.rows * cols || !data) {
    std::fprintf(stderr, "FAIL image %ld bad table rows=%d cols=%d bytes=%d\n",
                 image_id, t.rows, cols, nbytes);
    std::exit(4);
  }
  t.bytes.assign((const uint8_t*)data, (const uint8_t*)data + nbytes);
  sqlite3_finalize(stmt);
  return t;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 5) {
    std::fprintf(stderr,
                 "usage: %s <db_path> <out_dir> <image_a> <image_b>\n",
                 argv[0]);
    return 1;
  }
  const std::string db_path = argv[1];
  const std::string out_dir = argv[2];
  const long image_a = std::atol(argv[3]);
  const long image_b = std::atol(argv[4]);

  const std::string uri = "file:" + db_path + "?immutable=1";
  sqlite3* db = nullptr;
  if (sqlite3_open_v2(uri.c_str(), &db,
                      SQLITE_OPEN_READONLY | SQLITE_OPEN_URI,
                      nullptr) != SQLITE_OK) {
    std::fprintf(stderr, "FAIL open %s\n", uri.c_str());
    return 2;
  }
  const Table ta = ReadTable(db, image_a);
  const Table tb = ReadTable(db, image_b);
  sqlite3_close(db);

  const std::string sha_a =
      fairmatch::Sha256Hex(ta.bytes.data(), ta.bytes.size());
  const std::string sha_b =
      fairmatch::Sha256Hex(tb.bytes.data(), tb.bytes.size());
  fairmatch::WriteFileBytes(out_dir + "/a.u8", ta.bytes.data(),
                            ta.bytes.size());
  fairmatch::WriteFileBytes(out_dir + "/b.u8", tb.bytes.data(),
                            tb.bytes.size());

  char manifest[1024];
  std::snprintf(manifest, sizeof(manifest),
                "{\n"
                "  \"source_db\": \"%s\",\n"
                "  \"image_a\": %ld,\n"
                "  \"rows_a\": %d,\n"
                "  \"sha256_a\": \"%s\",\n"
                "  \"image_b\": %ld,\n"
                "  \"rows_b\": %d,\n"
                "  \"sha256_b\": \"%s\",\n"
                "  \"cols\": 128,\n"
                "  \"dtype\": \"uint8\"\n"
                "}\n",
                db_path.c_str(), image_a, ta.rows, sha_a.c_str(), image_b,
                tb.rows, sha_b.c_str());
  fairmatch::WriteFileBytes(out_dir + "/manifest.json", manifest,
                            std::strlen(manifest));
  std::printf("FIXTURE image_a=%ld rows_a=%d sha_a=%s\n", image_a, ta.rows,
              sha_a.c_str());
  std::printf("FIXTURE image_b=%ld rows_b=%d sha_b=%s\n", image_b, tb.rows,
              sha_b.c_str());
  return 0;
}
