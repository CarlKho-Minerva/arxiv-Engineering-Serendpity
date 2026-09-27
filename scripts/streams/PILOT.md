# Stream archive pilot (2026-09-27)

One 70.9-minute 1080p30 stream (18.6 GB) from the carlcrafters Takeout, processed locally.

| stage | where | time for 70.9 min | per stream-minute |
|---|---|---|---|
| extract mp4 from Takeout zip | PC, D: | 227 s | 3.2 s |
| sample 1 frame / 10 s (keyframes only, 1024 px) | PC CPU | 61 s (425 frames) | 0.9 s |
| scene-change detection | PC CPU | 64 s (101 changes) | 0.9 s |
| audio to 16 kHz mono | PC CPU | 2 s | 0.03 s |
| caption each frame (Gemma 4 31B AWQ, vLLM, eGPU, 4 concurrent) | PC GPU1 | 195 s, 0.46 s/frame, 425/425 valid JSON | 2.7 s |
| transcribe (mlx-whisper large-v3-turbo) | office Mac | 88 s (48.6x realtime, 3,866 words) | 1.2 s |

Projection for the whole archive (about 700 h = 42,000 min): extraction ~37 h (disk-bound), frame captions at 1/10 s ~32 GPU-hours on one card (252k frames, ~25 GB of JPEGs), transcription ~14 h on the Mac. Stages overlap, so roughly two days of wall-clock on one GPU. A first pass at 1 frame / 2 min (~3 GPU-hours) can classify every video (gameplay, work, camera) so the dense pass runs only where it adds information.

Pilot frame labels: 410/425 gameplay with the game named (four titles), mean 0.94 people visible (face cam).
