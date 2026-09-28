"""SigLIP 2 so400m NaFlex image embeddings for every keyframe -> data/streams/<key>/siglip.npy (N x 1152, fp16,
L2-normalized). Text queries embed into the same space, which is what makes "search by description" and
zero-shot game/app labels work later without touching the video again. 576 patches keeps the screen's aspect
ratio at ~0.05 s/frame on the M5 Max (measured 09-27).
"""
import os

import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

from common import ROOT, failed_twice, ledger, loop, synced_keys, upstream_done

STAGE = "siglip"
MODEL_ID = "google/siglip2-so400m-patch16-naflex"
PATCHES = 576
BATCH = 16
model = AutoModel.from_pretrained(MODEL_ID, torch_dtype=torch.float16).to("mps").eval()
proc = AutoProcessor.from_pretrained(MODEL_ID)


@torch.no_grad()
def embed(paths):
    out = []
    for i in range(0, len(paths), BATCH):
        ims = [Image.open(p).convert("RGB") for p in paths[i:i + BATCH]]
        x = proc(images=ims, return_tensors="pt", max_num_patches=PATCHES)
        x = {k: v.to("mps") for k, v in x.items()}
        x["pixel_values"] = x["pixel_values"].half()
        e = model.get_image_features(**x)
        e = getattr(e, "pooler_output", e)
        out.append(torch.nn.functional.normalize(e.float(), dim=-1).cpu().numpy().astype(np.float16))
    return np.concatenate(out) if out else np.zeros((0, 1152), np.float16)


def todo():
    done, bad = ledger(STAGE), failed_twice(STAGE)
    return [k for k in synced_keys() if k not in done and k not in bad]


def work(key):
    d = ROOT / key
    frames = sorted(os.listdir(d / "kf"))
    e = embed([str(d / "kf" / f) for f in frames])
    np.save(d / "siglip.npy", e)
    return {"frames": len(frames), "dim": int(e.shape[1]) if len(e) else 0}


if __name__ == "__main__":
    loop(STAGE, todo, work, done_flag=lambda: upstream_done(STAGE))
