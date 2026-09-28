#!/bin/bash
# forge-m5-48 (home, wired next to the PC) runs every per-video stage; the PC keeps all data (C:\streams\out).
# Start: nohup ~/streams-worker/scripts/streams/run_worker.sh >/dev/null 2>&1 &
# Stop:  touch ~/streams-worker/data/streams/_state/STOP
cd "$(dirname "$0")" || exit 1
export PATH=/opt/homebrew/bin:$PATH
export PC_HOST=Carlk@10.112.32.19          # the PC's LAN address: direct, not the relayed tailnet
export STREAMS_PUSH=1 STREAMS_FULL_PULL=1
export RG_DIR=~/streams-worker/recall_glasses JUDGE_VLLM_URL=http://100.95.29.20:8000
export PY=../../.venv/bin/python RG=../../.venv/bin/python
exec ./supervise.sh
