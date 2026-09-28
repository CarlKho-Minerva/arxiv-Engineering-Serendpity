#!/bin/bash
# Keep every Mac stage of the stream pipeline alive. Restarts a stage that died (unless its STOP file exists
# or it logged "all done"), logs every restart to data/streams/_state/supervise.log, and writes
# supervise.json each minute so the morning report (and anyone else) can see what is running.
# Start: nohup scripts/streams/supervise.sh >/dev/null 2>&1 &     Stop everything: touch data/streams/_state/STOP
cd "$(dirname "$0")" || exit 1
PY=${PY:-../../.venv/bin/python}
RG=${RG:-~/CODELocalProjects/recall-glasses/.venv/bin/python}
ST=../../data/streams/_state
STAGES="sync audio whisper ocr siglip vjepa anyjev relate"   # bash 3.2 on macOS: no associative arrays
cmd_for() { if [ "$1" = relate ]; then echo "$RG -u mac_relate.py"; else echo "$PY -u mac_$1.py"; fi; }
LIGHT="sync anyjev"   # network / HTTP only; the rest load the Mac GPU or CPU hard
# Carl's laptop: 09-28 02:18 the pipeline drained it to 1 % on battery and it slept until 06:27. On battery the heavy
# stages are stopped and not restarted; the light ones run only above 50 %. Everything resumes on AC.
power() { pmset -g batt | head -1 | grep -q "AC Power" && echo ac || echo "battery $(pmset -g batt | grep -o '[0-9]*%' | head -1 | tr -d %)"; }
is_light() { case " $LIGHT " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
while true; do
  [ -e "$ST/STOP" ] && { echo "$(date +%FT%T) STOP file, supervisor exits" >> "$ST/supervise.log"; exit 0; }
  pw=$(power); pct=${pw#battery }
  status="{\"power\":\"$pw\","
  for s in $STAGES; do
    pid=$(pgrep -f "python[^ ]* -u mac_$s.py" | head -1)   # the python process itself, not any shell that mentions it
    if [ "$pw" != ac ] && { ! is_light $s || [ "$pct" -lt 50 ]; }; then
      if [ -n "$pid" ]; then pkill -f "python[^ ]* -u mac_$s.py"; echo "$(date +%FT%T) stopped $s ($pw)" >> "$ST/supervise.log"; fi
      status+="\"$s\":\"held ($pw)\","
      continue
    fi
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
  case "$status" in *running*|*restarted*|*held*) ;; *) echo "$(date +%FT%T) every stage finished, supervisor exits" >> "$ST/supervise.log"; exit 0 ;; esac
  sleep 60
done
