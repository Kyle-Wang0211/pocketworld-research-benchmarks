// Scratch (not in the patch): run the PATCHED planArchivedRefeed read-only on the real capture dirs
// and print, per refeed order index (= the refeed ledger frameId), the trust bit.
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:pocketworld_flutter/official_capture/sfm_resume.dart' as sfm_resume;

void main() {
  test('plan', () async {
    final out = <String, Object?>{};
    for (final dir in Platform.environment['CAPS']!.split(':')) {
      final plan = await sfm_resume.planArchivedRefeed(dir);
      out[dir.split('/').last] = {
        'notes': plan.deviceTrust?.notes,
        'frames': [
          for (var i = 0; i < plan.ordered.length; i++)
            {
              'fid': i,
              'photo': plan.ordered[i].jpegPath.split('/').last,
              'trusted': plan.ordered[i].input!.devicePoseTrusted,
              'session': plan.ordered[i].input!.deviceSessionId,
            },
        ],
      };
    }
    File(Platform.environment['OUT']!).writeAsStringSync(jsonEncode(out));
  });
}
