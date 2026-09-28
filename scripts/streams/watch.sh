#!/bin/bash
# One watch window over the stream pipeline: exits (and says why) on the first anomaly, or after MAX_MIN minutes.
# Anomalies: PC Step 0 / captions status not updated for 10 min while running; new lines in any Mac *_failed.jsonl;
# more than 3 supervisor restarts in the window; PC unreachable twice in a row.
ST="$(cd "$(dirname "$0")/../../data/streams/_state" && pwd)"
MAX_MIN=${1:-60}
start=$(date +%s)
fails0=$(cat "$ST"/*_failed.jsonl 2>/dev/null | wc -l | tr -d ' ')
rest0=$(grep -c restarted "$ST/supervise.log" 2>/dev/null || echo 0)
miss=0
age() { python3 -c "import sys,json,datetime as d; t=json.loads(sys.stdin.read())
ts=d.datetime.strptime(t['ts'],'%Y-%m-%dT%H:%M:%S%z'); print(int((d.datetime.now(d.timezone.utc)-ts).total_seconds()), t.get('phase'))"; }
while true; do
  now=$(date +%s)
  [ $(( (now - start) / 60 )) -ge "$MAX_MIN" ] && { echo "HEARTBEAT: $MAX_MIN min, no anomaly"; exit 0; }
  for f in step0_status.json captions_status.json; do
    out=$(ssh -o ConnectTimeout=15 PC "type D:\\streams\\$f" 2>/dev/null | age 2>/dev/null)
    if [ -z "$out" ]; then
      miss=$((miss + 1)); [ $miss -ge 4 ] && { echo "ANOMALY: PC unreachable or $f unreadable"; exit 1; }
      continue
    fi
    miss=0
    set -- $out
    [ "$2" = "done" ] && continue
    [ "$1" -gt 600 ] && { echo "ANOMALY: PC $f last updated $1 s ago (phase $2)"; exit 1; }
  done
  f1=$(cat "$ST"/*_failed.jsonl 2>/dev/null | wc -l | tr -d ' ')
  [ "$f1" -gt "$fails0" ] && { echo "ANOMALY: $((f1 - fails0)) new Mac stage failures:"; tail -n $((f1 - fails0)) -q "$ST"/*_failed.jsonl | cut -c1-200 | tail -5; exit 1; }
  r1=$(grep -c restarted "$ST/supervise.log" 2>/dev/null || echo 0)
  [ $((r1 - rest0)) -gt 3 ] && { echo "ANOMALY: $((r1 - rest0)) supervisor restarts"; tail -5 "$ST/supervise.log"; exit 1; }
  [ -e "$ST/PC_CAPTIONS_DONE" ] && [ -e "$ST/PC_STEP0_DONE" ] && grep -q "every stage finished" "$ST/supervise.log" 2>/dev/null && { echo "DONE: every stage finished"; exit 0; }
  sleep 120
done
