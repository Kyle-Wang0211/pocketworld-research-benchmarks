// box_ref.dart — the authority itself: the app's SelectionBox.contains() evaluated over deterministic points.
// Writes box.txt (c, s, rot9), pts.f64 (n×3) and bits.u8 (contains) for the C++ BoxFilter parity check.
import 'dart:io';
import 'dart:typed_data';

import 'file:///Users/kaidongwang/Developer/pw-dense-stage/lib/official_capture/selection_box.dart';

void main(List<String> args) {
  final out = args[0];
  // a box over the fixture cloud's median with a 30° yaw (the viewer's rotate-rail path -> withYaw)
  final box = SelectionBox.withYaw(cx: -0.71, cy: -0.16, cz: -0.35, sx: 1.0, sy: 0.8, sz: 1.2, yawDeg: 30);
  const n = 200000;
  var s = 12345;
  double next() {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return s / 0x7fffffff * 6 - 3;
  }
  final pts = Float64List(n * 3);
  final bits = Uint8List(n);
  var inside = 0;
  for (var i = 0; i < n; i++) {
    final x = next(), y = next(), z = next();
    pts[i * 3] = x;
    pts[i * 3 + 1] = y;
    pts[i * 3 + 2] = z;
    final c = box.contains(x, y, z);
    bits[i] = c ? 1 : 0;
    if (c) inside++;
  }
  File('$out/box.txt').writeAsStringSync('${box.cx} ${box.cy} ${box.cz} ${box.sx} ${box.sy} ${box.sz} ${box.rot.join(' ')}\n');
  File('$out/pts.f64').writeAsBytesSync(pts.buffer.asUint8List());
  File('$out/bits.u8').writeAsBytesSync(bits);
  stdout.writeln('dart: $n points, inside $inside; rot=${box.rot}');
}
