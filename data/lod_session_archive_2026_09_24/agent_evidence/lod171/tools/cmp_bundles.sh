#!/bin/sh
# cmp_bundles.sh A B : per-file comparison; Mach-O compared with signatures removed (copies in tmp).
A="$1"; B="$2"; T=$(mktemp -d)
(cd "$A" && find . -type f | LC_ALL=C sort) > $T/a; (cd "$B" && find . -type f | LC_ALL=C sort) > $T/b
comm -12 $T/a $T/b | grep -v "_CodeSignature/CodeResources$" | while read f; do
  if file "$A/$f" | grep -q "Mach-O"; then
    cp "$A/$f" $T/x; cp "$B/$f" $T/y; codesign --remove-signature $T/x 2>/dev/null; codesign --remove-signature $T/y 2>/dev/null
    ha=$(shasum -a 256 $T/x | cut -d' ' -f1); hb=$(shasum -a 256 $T/y | cut -d' ' -f1); k=MACHO
  else
    ha=$(shasum -a 256 "$A/$f" | cut -d' ' -f1); hb=$(shasum -a 256 "$B/$f" | cut -d' ' -f1); k=FILE
  fi
  [ "$ha" = "$hb" ] && echo "SAME $k $f" || echo "DIFF $k $f ${ha%${ha#????????????}} ${hb%${hb#????????????}}"
done
echo "ONLY_IN_A:"; comm -23 $T/a $T/b; echo "ONLY_IN_B:"; comm -13 $T/a $T/b
rm -rf $T
