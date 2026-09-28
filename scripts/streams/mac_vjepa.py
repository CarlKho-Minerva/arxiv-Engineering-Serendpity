"""V-JEPA 2 ViT-L (facebook/vjepa2-vitl-fpc64-256, MIT) motion features from the Step 0 proxy video.

One 16-frame clip at 4 fps (4 s window) centred on every 60 s mark -> data/streams/<key>/vjepa.npz with
  t      clip centre times (s)
  mean   N x 1024 mean over all 2048 tokens (fp16)
  grid   N x 4 x 1024: tokens mean-pooled over time into a 2x2 spatial grid (fp16), for a latent predictor
Frames are squashed to 256x256 (no crop) so the whole screen stays in view. 0.15 s/clip at batch 8 on the
M5 Max (measured 09-27), so one clip per minute costs ~1.7 h for the whole archive.
"""
import subprocess

import numpy as np
import torch
from transformers import AutoModel

from common import ROOT, failed_twice, ledger, loop, synced_keys, upstream_done

STAGE = "vjepa"
MODEL_ID = "facebook/vjepa2-vitl-fpc64-256"
EVERY_S, FPS, T = 60, 4, 16
model = AutoModel.from_pretrained(MODEL_ID, dtype=torch.float16).to("mps").eval()
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 1, 3, 1, 1)


def clips(path):
    """Decode only the 4 s windows around each 60 s mark (not the whole video) -> list of (centre_s, 16 frames)."""
    vf = f"fps={FPS},select='lt(mod(t+2,{EVERY_S}),4)',scale=256:256"
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True)
    raw = r.stdout
    if r.returncode != 0 and len(raw) == 0:
        return []  # sub-second clips: nothing to embed
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 256, 256, 3)
    out, i, c = [], 0, 0
    while i < len(fr):
        n = T // 2 if c == 0 else T  # the window around t=0 has only its second half
        g = fr[i:i + n]
        i += n
        if len(g) < T:
            g = np.concatenate([g, np.repeat(g[-1:], T - len(g), 0)])
        out.append((c * EVERY_S, g))
        c += 1
    return out


@torch.no_grad()
def work(key):
    cl = clips(ROOT / key / "proxy.mp4")
    means, grids = [], []
    for i in range(0, len(cl), 8):
        x = torch.from_numpy(np.stack([g for _, g in cl[i:i + 8]])).permute(0, 1, 4, 2, 3).float() / 255
        x = ((x - MEAN) / STD).half().to("mps")
        h = model.get_vision_features(x).float()  # B x (T/2 * 16 * 16) x 1024
        b = h.shape[0]
        g = h.view(b, T // 2, 16, 16, 1024).mean(1).view(b, 2, 8, 2, 8, 1024).mean((2, 4)).reshape(b, 4, 1024)
        means.append(h.mean(1).cpu().numpy().astype(np.float16))
        grids.append(g.cpu().numpy().astype(np.float16))
    t = np.array([c for c, _ in cl], np.float32)
    np.savez(ROOT / key / "vjepa.npz", t=t, mean=np.concatenate(means) if means else np.zeros((0, 1024), np.float16),
             grid=np.concatenate(grids) if grids else np.zeros((0, 4, 1024), np.float16))
    return {"clips": len(cl)}


def todo():
    done, bad = ledger(STAGE), failed_twice(STAGE)
    have = set(ledger("sync_proxy")) | {k for k in synced_keys() if (ROOT / k / "proxy.mp4").exists()}
    return [k for k in synced_keys() if k in have and k not in done and k not in bad]


if __name__ == "__main__":
    loop(STAGE, todo, work, done_flag=lambda: upstream_done(STAGE), outputs=("vjepa.npz",))
