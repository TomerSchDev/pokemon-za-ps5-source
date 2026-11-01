#!/bin/sh
# Background heartbeat for the za-atlas claim board: every 10 minutes, stop on "lost" (exit 3).
AGENT="$1"; PKG="$2"; LOG="$3"
cd "C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port" || exit 1
while true; do
  OUT=$(py -3 -I tools/za-atlas/claim.py heartbeat --agent "$AGENT" --package "$PKG"); RC=$?
  echo "$(date +%H:%M:%S) rc=$RC $OUT" >> "$LOG"
  if [ "$RC" -eq 3 ]; then echo "LOST" >> "$LOG"; exit 3; fi
  sleep 600
done
