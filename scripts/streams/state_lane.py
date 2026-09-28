"""Pitch 6 (exploratory): the stream archive as a state lane, and a first next-state test.

build   per 5-minute bin of every processed stream -> data/derived/stream_bins.parquet (private)
          time            stream create timestamp + bin offset (UTC); create time may lag the live start
          sig_pca_*       SigLIP 2 frame embeddings, bin mean, PCA-64 fit on train-period bins only
          vj_pca_*        V-JEPA 2 clip embeddings (1/min), bin mean, PCA-32 fit on train-period bins only
          type_*          histogram over 64 k-means "screen types" (SigLIP frames, fit on train-period frames)
          aj_*            AnyJev L0 probabilities (activity x11, working, social, mode x4, focus EV, novel)
          speech_frac, rms_db, silent_frac, scene_change_mean/max (1 - cosine between consecutive frames),
          ocr_lines, game_share (Gemma captions)
test    predict bin t+1's standardized state (sig_pca + aj) from bin t (ridge) and bins t-3..t (ridge on the
        stacked window), against persistence (copy bin t) and the train mean; chronological split by stream date.
        Reports R^2 relative to persistence, and whether prediction error ("surprise") rises when the AnyJev
        activity changes (a sanity check that the state tracks what Carl is doing).
Outputs: results/streams_state_lane.json (aggregates only).
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import MiniBatchKMeans
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "streams"
OUT = REPO / "data" / "derived" / "stream_bins.parquet"
BIN = 300
TRAIN_END, TEST_START = "2024-07-01", "2025-01-01"
ACT = ["coding", "writing", "design", "reading", "call", "presenting", "talking", "gaming", "media", "idle", "other"]


def created(m):
    c = m.get("created") or (m.get("resolved_by_duration") or {}).get("created")
    return datetime.fromisoformat(c.replace("Z", "+00:00")) if c else None


def read_jsonl(p):
    return [json.loads(line) for line in open(p)] if p.exists() else []


def build():
    raw, frames_train = [], []
    for d in sorted(ROOT.iterdir()):
        if not (d / "siglip.npy").exists() or not (d / "meta.json").exists():
            continue
        m = json.load(open(d / "meta.json"))
        t0 = created(m)
        if t0 is None:
            continue
        sig = np.load(d / "siglip.npy").astype(np.float32)
        if not len(sig):
            continue
        vj = np.load(d / "vjepa.npz") if (d / "vjepa.npz").exists() else None
        aj = {r["bin"]: r for r in read_jsonl(d / "anyjev.jsonl")}
        au = json.load(open(d / "audio.json")) if (d / "audio.json").exists() else {}
        caps = read_jsonl(d / "captions.jsonl")
        ocr = read_jsonl(d / "ocr.jsonl")
        speech = au.get("speech_segments", [])
        rms = np.array(au.get("rms_db_per_s", []), dtype=np.float32)
        change = np.r_[np.nan, 1 - (sig[1:] * sig[:-1]).sum(1)] if len(sig) > 1 else np.array([np.nan])
        dur = float(m.get("duration_s") or len(sig) * 10)
        for b in range(int(np.ceil(dur / BIN))):
            lo, hi = b * BIN, (b + 1) * BIN
            fi = slice(lo // 10, hi // 10)
            if sig[fi].shape[0] == 0:
                continue
            row = {"key": d.name, "bin": b, "time": t0 + timedelta(seconds=lo), "date": t0.date().isoformat(),
                   "worklike": bool(m.get("worklike")), "sig_mean": sig[fi].mean(0)}
            if vj is not None and len(vj["t"]):
                sel = (vj["t"] >= lo) & (vj["t"] < hi)
                row["vj_mean"] = vj["mean"][sel].astype(np.float32).mean(0) if sel.any() else None
            if b in aj:
                for k, v in aj[b].items():
                    if k.startswith(("p_", "ev_")):
                        row["aj_" + k.split("_", 1)[1]] = v
            sp = sum(max(0, min(e, hi) - max(s, lo)) for s, e in speech)
            row["speech_frac"] = sp / min(BIN, max(1.0, dur - lo))
            r = rms[lo:hi]
            row["rms_db"] = float(r.mean()) if len(r) else np.nan
            row["silent_frac"] = float((r < -50).mean()) if len(r) else np.nan
            ch = change[fi]
            row["scene_change_mean"] = float(np.nanmean(ch)) if np.isfinite(ch).any() else np.nan
            row["scene_change_max"] = float(np.nanmax(ch)) if np.isfinite(ch).any() else np.nan
            row["ocr_lines"] = float(np.mean([len(o["lines"]) for o in ocr if lo <= o["t"] < hi] or [np.nan]))
            cb = [c for c in caps if lo <= c["t"] < hi and "activity" in c]
            row["game_share"] = float(np.mean(["game" in str(c["activity"]).lower() for c in cb])) if cb else np.nan
            raw.append(row)
            if row["date"] < TRAIN_END:
                frames_train.append(sig[fi])
    df = pd.DataFrame(raw)
    if df.empty:
        raise SystemExit("no processed streams yet")
    tr = df["date"] < TRAIN_END
    S = np.stack(df["sig_mean"].values)
    pca = PCA(64, random_state=0).fit(S[tr.values] if tr.sum() >= 64 else S)
    df = pd.concat([df, pd.DataFrame(pca.transform(S), index=df.index, columns=[f"sig_pca_{i}" for i in range(64)])], axis=1)
    ft = np.concatenate(frames_train) if frames_train else S
    km = MiniBatchKMeans(64, random_state=0, n_init=3).fit(ft)
    hist = []
    for _, r in df.iterrows():
        sig = np.load(ROOT / r["key"] / "siglip.npy").astype(np.float32)[r["bin"] * 30:(r["bin"] + 1) * 30]
        hist.append(np.bincount(km.predict(sig), minlength=64) / max(1, len(sig)))
    df = pd.concat([df, pd.DataFrame(np.stack(hist), index=df.index, columns=[f"type_{i}" for i in range(64)])], axis=1)
    has_vj = df["vj_mean"].notna() if "vj_mean" in df else pd.Series(False, index=df.index)
    if has_vj.sum() >= 32:
        V = np.stack(df.loc[has_vj, "vj_mean"].values)
        vtr = (df.loc[has_vj, "date"] < TRAIN_END).values
        vp = PCA(32, random_state=0).fit(V[vtr] if vtr.sum() >= 32 else V)
        Z = pd.DataFrame(vp.transform(V), index=df.index[has_vj.values], columns=[f"vj_pca_{i}" for i in range(32)])
        df = pd.concat([df, Z.reindex(df.index)], axis=1)
    df = df.drop(columns=[c for c in ("sig_mean", "vj_mean") if c in df])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT)
    print(f"bins {len(df)} from {df['key'].nunique()} streams; train-period bins {int(tr.sum())}; columns {df.shape[1]}")
    return df


def test(df):
    df = df.sort_values(["key", "bin"]).reset_index(drop=True)
    aj_cols = [c for c in df.columns if c.startswith("aj_")]
    cols = [f"sig_pca_{i}" for i in range(64)] + aj_cols
    X = df[cols].astype(float)
    tr_mask = df["date"] < TRAIN_END
    mu, sd = X[tr_mask].mean(), X[tr_mask].std().replace(0, 1)
    Z = ((X - mu) / sd).fillna(0).values
    rows = []
    for key, g in df.groupby("key", sort=False):
        idx = g.index.values
        for j in range(len(idx) - 1):
            hist = [idx[max(0, j - k)] for k in (3, 2, 1, 0)]
            rows.append((idx[j], idx[j + 1], hist, df.at[idx[j], "date"]))
    if not rows:
        return {"pairs": 0}
    cur = np.array([r[0] for r in rows]); nxt = np.array([r[1] for r in rows]); dates = np.array([r[3] for r in rows])
    win = np.stack([Z[r[2]].ravel() for r in rows])
    tr, te = dates < TRAIN_END, dates >= TEST_START
    if tr.sum() < 50 or te.sum() < 20:
        return {"pairs": int(len(rows)), "train_pairs": int(tr.sum()), "test_pairs": int(te.sum()), "note": "too few pairs yet"}
    y = Z[nxt]
    mse = lambda p: float(((p - y[te]) ** 2).mean())
    res = {"pairs": int(len(rows)), "train_pairs": int(tr.sum()), "test_pairs": int(te.sum()), "dims": len(cols),
           "mse_persistence": mse(Z[cur][te]), "mse_train_mean": mse(np.tile(y[tr].mean(0), (te.sum(), 1)))}
    r1 = Ridge(alpha=10).fit(Z[cur][tr], y[tr]); p1 = r1.predict(Z[cur][te]); res["mse_ridge_t"] = mse(p1)
    r4 = Ridge(alpha=10).fit(win[tr], y[tr]); p4 = r4.predict(win[te]); res["mse_ridge_window4"] = mse(p4)
    for k in ("mse_train_mean", "mse_ridge_t", "mse_ridge_window4"):
        res["r2_vs_persistence_" + k[4:]] = 1 - res[k] / res["mse_persistence"]
    act = [c for c in aj_cols if c.startswith("aj_activity_")]
    if act:
        a = df[act].fillna(0).values
        changed = a[cur].argmax(1) != a[nxt].argmax(1)
        surprise = ((p4 - y[te]) ** 2).mean(1)
        ch_te = changed[te]
        if ch_te.any() and (~ch_te).any():
            res["surprise_when_activity_changes"] = float(surprise[ch_te].mean())
            res["surprise_when_same_activity"] = float(surprise[~ch_te].mean())
            res["activity_change_share_test"] = float(ch_te.mean())
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-only", action="store_true")
    a = ap.parse_args()
    df = pd.read_parquet(OUT) if a.test_only else build()
    res = {"generated": datetime.now(timezone.utc).isoformat(), "bins": int(len(df)), "streams": int(df["key"].nunique()),
           "split": {"train_end": TRAIN_END, "test_start": TEST_START}, "status": "exploratory", **test(df)}
    (REPO / "results").mkdir(exist_ok=True)
    json.dump(res, open(REPO / "results" / "streams_state_lane.json", "w"), indent=1)
    print(json.dumps(res, indent=1))
