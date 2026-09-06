#!/bin/bash
# Serve the verdict pages on 127.0.0.1:8931, detached so it outlives the shell
# that started it. The pages cannot be opened as files: 60-90M points are far too
# large to inline, so the viewer fetches .pos/.col over HTTP.
DIR="$(cd "$(dirname "$0")" && pwd)"
if lsof -nP -iTCP:8931 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "already serving on 8931"; exit 0
fi
nohup python3 -m http.server 8931 --bind 127.0.0.1 --directory "$DIR" \
  >> "$DIR/serve.log" 2>&1 &
disown
sleep 1
lsof -nP -iTCP:8931 -sTCP:LISTEN >/dev/null 2>&1 && echo "serving http://127.0.0.1:8931/ (pid $!)" || { echo "FAILED - see $DIR/serve.log"; exit 1; }
