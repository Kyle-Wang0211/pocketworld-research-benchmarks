#!/bin/bash
# 装机前核对(只读)。用法: preinstall_checks.sh <Runner.app> [期望 bundle id]
set -u
APP="$1"; WANT="${2:-com.kyle.arloopbench}"; fail=0
T=$(mktemp -d)
ok(){ echo "  ok   $*"; }; no(){ echo "  FAIL $*"; fail=1; }
# 1 bundle id
got=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP/Info.plist" 2>/dev/null)
[ "$got" = "$WANT" ] && ok "1 bundle id = $got" || no "1 bundle id = '$got' (want $WANT)"
# 2 codesign
if codesign --verify --deep --strict "$APP" 2>"$T/cs.err"; then ok "2 codesign --verify --deep --strict"; else no "2 codesign: $(tr '\n' ' ' < "$T/cs.err")"; fi
# 3 nm on Runner executable (先落盘再 grep,不用管道 grep -q)
nm -g "$APP/Runner" > "$T/nm.txt" 2>/dev/null
for s in pwlod_viewer_create pwlod_build_from_ply pwlod_run pwlod_version; do
  n=$(awk -v s="_$s" '$3==s && $2=="T"' "$T/nm.txt" | wc -l | tr -d ' ')
  [ "$n" = 1 ] && ok "3 $s defined (T) x1" || no "3 $s defined count=$n"
done
strings -a "$APP/Runner" > "$T/str.txt"
n=$(grep -c -F 'afb521e6 abi=2' "$T/str.txt"); [ "$n" -ge 1 ] && ok "3 version string 'afb521e6 abi=2' x$n" || no "3 version string missing"
# wgpuCreateInstance: 所有 Mach-O 镜像里的定义合计
total=0
while IFS= read -r f; do
  file -b "$f" | grep -q 'Mach-O' || continue
  c=$(nm -g -U "$f" 2>/dev/null > "$T/one.txt"; awk '$3=="_wgpuCreateInstance" && ($2=="T"||$2=="S"||$2=="D")' "$T/one.txt" | wc -l | tr -d ' ')
  [ "$c" != 0 ] && echo "       wgpuCreateInstance defined in ${f#$APP/}: $c"
  total=$((total + c))
done < <(find "$APP" -type f ; for x in ${EXTRA_OBJS:-}; do echo "$x"; done)
[ "$total" = 1 ] && ok "3 wgpuCreateInstance defined once across all images" || no "3 wgpuCreateInstance defined $total times"
rm -rf "$T"
[ $fail = 0 ] && echo "PREINSTALL_CHECKS_PASS" || echo "PREINSTALL_CHECKS_FAIL"
exit $fail
