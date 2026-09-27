"""Minimal MLX backend for AnyJev: next-token log-probs from a local mlx_lm model.

AnyJev's Decider only needs `next_token_logprobs(prompts, token_ids)` -> list of
arrays (one per prompt, one log-prob per requested token id) plus a `tokenizer`
and a `name`. This runs raw / L0 / L1 on Apple Silicon with no server.
"""
from __future__ import annotations

from typing import List, Sequence

import mlx.core as mx
import numpy as np
from mlx_lm import load


class MLXBackend:
    def __init__(self, model_name: str):
        self.name = model_name
        self.model, self.tokenizer = load(model_name)

    def next_token_logprobs(self, prompts: Sequence[str], token_ids: Sequence[Sequence[int]]) -> List[np.ndarray]:
        out = []
        for p, ids in zip(prompts, token_ids):
            toks = mx.array(self.tokenizer.encode(p))[None]
            logits = self.model(toks)[0, -1].astype(mx.float32)
            lp = logits - mx.logsumexp(logits)
            lp = np.asarray(lp)
            out.append(np.array([lp[i] for i in ids], dtype=np.float64))
        return out
