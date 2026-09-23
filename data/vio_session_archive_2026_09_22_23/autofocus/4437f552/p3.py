import io, sys
for p, both in (
    ("/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/prod-af-20260923/ios/Runner.xcodeproj/project.pbxproj", True),
    ("/Users/kaidongwang/Developer/arloopbench/ios/Runner.xcodeproj/project.pbxproj", False),
):
    s = io.open(p, encoding="utf-8").read()
    a = '"-Wl,-u,_pw_camera_slot_focus_report",'
    n = a + '\n\t\t\t\t\t"-Wl,-u,_pw_camera_slot_focus_nudge",'
    if '_pw_camera_slot_focus_nudge' in s:
        print("already", p); continue
    c = s.count(a)
    if c == 0: sys.exit("no -u anchor in " + p)
    s = s.replace(a, n)
    added = c
    if both:
        b = '"-Wl,-exported_symbol,_pw_camera_slot_focus_report",'
        nb = b + '\n\t\t\t\t\t"-Wl,-exported_symbol,_pw_camera_slot_focus_nudge",'
        cb = s.count(b)
        if cb == 0: sys.exit("no exported anchor in " + p)
        s = s.replace(b, nb)
        added = (c, cb)
    io.open(p, "w", encoding="utf-8").write(s)
    print("ok", p, added)
