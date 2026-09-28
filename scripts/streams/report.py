"""Morning report for the stream-archive run: progress per stage and every pitch's aggregate numbers.

Writes results/private/streams/REPORT.md (aggregates only, but kept private because it names streams' years and
counts next to Carl's data). Re-run any time; it reads ledgers and results files, never raw content.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ST = REPO / "data" / "streams" / "_state"
RES = REPO / "results"


def n(stage):
    p = ST / f"{stage}.jsonl"
    return sum(1 for _ in open(p)) if p.exists() else 0


def j(p):
    try:
        return json.load(open(p))
    except Exception:
        return None


def main():
    man = j(ST / "manifest.json") or []
    total = len(man)
    s0 = j(ST / "pc_step0_status.json") or {}
    cap = j(ST / "pc_captions_status.json") or {}
    L = [f"# Stream archive run: status {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    L += ["## Pipeline", "", "| stage | videos done | of |", "|---|---|---|"]
    L.append(f"| PC Step 0 (read once) | {s0.get('done')} ({s0.get('hours_done')} h), failed {s0.get('failed')} | {total} |")
    L.append(f"| PC Gemma captions | {cap.get('videos_done')} this run ({cap.get('frames_done')} frames), paused: {cap.get('paused_for')} | {total} |")
    for st in ("sync", "sync_captions", "audio", "whisper", "ocr", "siglip", "vjepa", "anyjev", "relate"):
        L.append(f"| Mac {st} | {n(st)} (failed twice: {sum(1 for _ in open(ST / f'{st}_failed.jsonl')) if (ST / f'{st}_failed.jsonl').exists() else 0} lines) | {total} |")
    w = [json.loads(line) for line in open(ST / "whisper.jsonl")] if (ST / "whisper.jsonl").exists() else []
    L += ["", f"Speech: {sum(1 for r in w if 'segments' in r)} videos transcribed, {sum(1 for r in w if r.get('skipped'))} silent, "
               f"{sum(r.get('words', 0) for r in w):,} words.", ""]
    for name, title in (("streams_state_lane.json", "Pitch 6: state lane"), ("streams_attention_games.json", "Pitches 3 + 7: attention and games"),
                        ("streams_speech.json", "Pitches 4 + 9: speech corpus and language model"), ("streams_qa_baseline.json", "Pitch 10: question set baseline"),
                        ("streams_adoption.json", "Pitch 2: H-ADOPT (confirmatory, run once)")):
        d = j(RES / name)
        L += [f"## {title}", "", "```json", json.dumps(d, indent=1)[:3000] if d else "not run yet", "```", ""]
    for name, title in (("pitch5_screenstudio_audit.md", "Pitch 5: Screen Studio audit"), ("pitch5_labeler_eval.md", "Pitch 5: public labeler eval")):
        p = RES / "private" / "streams" / name
        L += [f"## {title}", "", (p.read_text()[:2500] if p.exists() else "not written yet"), ""]
    ent = REPO / "data" / "derived" / "streams_watch_entities.jsonl"
    L += ["## Pitch 2 exposure side", "", f"watch titles with entity extraction done: {sum(1 for _ in open(ent)) if ent.exists() else 0}", ""]
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    L.append(f"repo HEAD {commit}; pre-registration tag streams-prereg-v1")
    out = RES / "private" / "streams" / "REPORT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L))
    print(out)


if __name__ == "__main__":
    main()
