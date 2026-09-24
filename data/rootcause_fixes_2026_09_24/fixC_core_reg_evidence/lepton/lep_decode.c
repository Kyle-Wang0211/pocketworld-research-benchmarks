// lep_decode.c — host decode of the product's vendored Lepton 0.5.8 archive
// (pw-dense-stage vendor/lepton_jpeg, bridge pw_lepton_bridge.h). Calls the
// exact entry the app uses for JPEG reconstruction
// (lib/official_capture/lepton_photo_archive_ffi_codec.dart:169-177,
//  pw_lepton_reconstruct_jpeg_file_cancellable). usage: lep_decode in.lep out.jpg ...
#include <stdio.h>
#include <stdint.h>
#include "pw_lepton_bridge.h"
int main(int argc, char** argv) {
  printf("lepton version=%s revision=%s\n", pw_lepton_version(), pw_lepton_revision());
  int bad = 0;
  for (int i = 1; i + 1 < argc; i += 2) {
    uint64_t us = 0;
    int32_t st = pw_lepton_reconstruct_jpeg_file_cancellable(
        argv[i], argv[i + 1], pw_lepton_cancellation_generation(), &us);
    if (st != 0) { fprintf(stderr, "FAIL %s: %s\n", argv[i], pw_lepton_error_message(st)); bad++; }
  }
  return bad ? 1 : 0;
}
