#!/bin/bash
# Keep every Mac stage of the stream pipeline alive. Restarts a stage that died (unless its STOP file exists
# or it logged "all done"), logs every restart to data/streams/_state/supervise.log, and writes
# supervise.json each minute so the morning report (and anyone else) can see what is running.
# Start: nohup scripts/streams/supervise.sh >/dev/null 2>&1 &     Stop everything: touch data/streams/_state/STOP
cd "$(dirname "$0")" || exit 1
PY=../../.venv/bin/python
RG=~/CODELocalProjects/recall-glasses/.venv/bin/python
ST=../../data/streams/_state
STAGES="sync audio whisper ocr siglip vjepa anyjev relate"   # bash 3.2 on macOS: no associative arrays
cmd_for() { if [ "$1" = relate ]; then echo "$RG -u mac_relate.py"; else echo "$PY -u mac_$1.py"; fi; }
while true; do
  [ -e "$ST/STOP" ] && { echo "$(date +%FT%T) STOP file, supervisor exits" >> "$ST/supervise.log"; exit 0; }
  status="{"
  for s in $STAGES; do
    pid=$(pgrep -f "mac_$s.py" | head -1)
    if [ -z "$pid" ]; then
      if [ -e "$ST/STOP_$s" ] || grep -q "all done\|all synced" "$ST/$s.log" 2>/dev/null; then
        state=finished
      else
        nohup $(cmd_for $s) >> "$ST/$s.out" 2>&1 &
        echo "$(date +%FT%T) restarted $s (was not running)" >> "$ST/supervise.log"
        state=restarted
      fi
    else
      state=running
    fi
    status+="\"$s\":\"$state\","
  done
  echo "${status%,},\"ts\":\"$(date +%FT%T%z)\"}" > "$ST/supervise.json"
  case "$status" in *running*|*restarted*) ;; *) echo "$(date +%FT%T) every stage finished, supervisor exits" >> "$ST/supervise.log"; exit 0 ;; esac
  sleep 60
done
