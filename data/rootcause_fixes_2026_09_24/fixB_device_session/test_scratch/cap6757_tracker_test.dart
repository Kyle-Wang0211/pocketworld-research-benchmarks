// Scratch (not in the patch): replay the page's real tracking-state telemetry of cap_1787733401226757
// (the same pose listener the patch hooks) through the PATCHED tracker; photos = hires_still events.
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:pocketworld_flutter/official_capture/device_pose_session.dart';

void main() {
  test('replay', () {
    final ev = (jsonDecode(File(Platform.environment['EV']!).readAsStringSync()) as List)
        .cast<Map<String, dynamic>>();
    final tr = DevicePoseSessionTracker(idPrefix: 'arkit-6757')..beginRun(reason: 'capture_run');
    final shots = <DevicePoseSessionEvidence>[];
    final live = <bool>[];
    var k = 0;
    String? state;
    for (final e in ev) {
      final t = (e['t'] as num).toDouble() / 1000.0;
      if (e['type'] == 'tracking') {
        state = e['state'] as String?;
        tr.observe(deviceTrackingPhaseFromArkitName(state), t);
      } else if (e['outcome'] == 'ok') {
        // pose stream is continuous: the current state holds at the shutter instant too
        tr.observe(deviceTrackingPhaseFromArkitName(state), t);
        shots.add(DevicePoseSessionEvidence(
            photoName: 'photo-$k', captureTimestamp: t, hasRecord: true,
            recordedSessionId: tr.sessionAt(t)));
        live.add(tr.isTrustedAt(t));
        k++;
      }
    }
    final plan = planDevicePoseTrust(shotsInOrder: shots);
    File(Platform.environment['OUT']!).writeAsStringSync(jsonEncode({
      'boundaries': [for (final b in tr.boundaries) {'id': b.sessionId, 'start': b.startTimestamp, 'reason': b.reason}],
      'live_trusted': live,
      'refeed_trusted': [for (final s in shots) plan.isTrusted(s.photoName)],
      'notes': plan.notes,
    }));
  });
}
