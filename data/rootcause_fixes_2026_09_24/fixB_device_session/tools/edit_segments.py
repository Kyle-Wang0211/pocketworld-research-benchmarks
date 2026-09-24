import sys
p=sys.argv[1]; s=open(p).read()
old="""      final names = <String>{};
      final fids = <int>{};
      var dup = false;
      for (final line in await f.readAsLines()) {
        if (line.trim().isEmpty) continue;
        try {
          final m = jsonDecode(line);
          if (m is! Map<String, dynamic>) continue;
          final p = m['jpegPath'];
          if (p is String && p.isNotEmpty) names.add(p.split('/').last);
          final fid = m['frameId'];
          if (fid is int && !fids.add(fid)) dup = true;
        } catch (_) {}
      }
      if (li == 0) {
        currentDup = dup;
        currentNames = names;
      }
      // frameId 重复 = 一份账被两个会话写过(frameId 每会话从 0 重数),不作证据。
      if (!dup && names.isNotEmpty) ledgerSets.add(names);"""
new="""      final names = <String>{};
      final fids = <int>{};
      var dup = false;
      // 按 frameId 回落切段:frameId 每个实拍会话从 0 重数
      // (official_aether_sfm_c.cc `frame_id = s->frames.size()`),改前的补拍会
      // 往同一份账本里接着写 ⇒ 回落处就是两次实拍的分界,每段各是一份证据。
      var segment = <String>{};
      int? lastFid;
      for (final line in await f.readAsLines()) {
        if (line.trim().isEmpty) continue;
        try {
          final m = jsonDecode(line);
          if (m is! Map<String, dynamic>) continue;
          final fid = m['frameId'];
          if (fid is int) {
            if (!fids.add(fid)) dup = true;
            if (lastFid != null && fid <= lastFid && segment.isNotEmpty) {
              ledgerSets.add(segment);
              segment = <String>{};
            }
            lastFid = fid;
          }
          final p = m['jpegPath'];
          if (p is String && p.isNotEmpty) {
            names.add(p.split('/').last);
            segment.add(p.split('/').last);
          }
        } catch (_) {}
      }
      if (segment.isNotEmpty) ledgerSets.add(segment);
      if (li == 0) {
        currentDup = dup;
        currentNames = names;
      }"""
assert s.count(old)==1; s=s.replace(old,new); open(p,'w').write(s)
