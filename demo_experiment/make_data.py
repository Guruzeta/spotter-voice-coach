"""Generate a fake (but realistic-looking) learning-rate sweep for the demo.

Story baked into the data:
- run_1: lr too low, learns slowly.
- run_2: solid baseline.
- run_3: best val loss (higher lr + long warmup), slight overfit late.
- run_4: same lr as run_3 but NO warmup -> loss spike + grad-norm blowup ~step 700, never fully recovers.
- run_5: lr too high -> diverges to NaN around step 3100.
"""
import csv
import math
import random
from pathlib import Path

ROOT = Path(__file__).parent
STEPS = list(range(0, 10001, 100))

RUNS = [
    dict(run_id="run_1", lr=1e-4, warmup_steps=1000, batch_size=64, weight_decay=0.1, grad_clip=0.0),
    dict(run_id="run_2", lr=3e-4, warmup_steps=1000, batch_size=64, weight_decay=0.1, grad_clip=0.0),
    dict(run_id="run_3", lr=6e-4, warmup_steps=2000, batch_size=64, weight_decay=0.1, grad_clip=0.0),
    dict(run_id="run_4", lr=6e-4, warmup_steps=0, batch_size=64, weight_decay=0.1, grad_clip=0.0),
    dict(run_id="run_5", lr=1.5e-3, warmup_steps=1000, batch_size=64, weight_decay=0.1, grad_clip=0.0),
]
SPEED = {"run_1": 0.25, "run_2": 0.55, "run_3": 0.75, "run_4": 0.6, "run_5": 0.8}
FLOOR = {"run_1": 3.35, "run_2": 3.02, "run_3": 2.91, "run_4": 3.18, "run_5": 3.0}


def lr_at(step, cfg):
    peak, warm = cfg["lr"], cfg["warmup_steps"]
    if warm and step < warm:
        return peak * step / warm
    progress = (step - warm) / max(1, STEPS[-1] - warm)
    return peak * 0.5 * (1 + math.cos(math.pi * progress))


def simulate(cfg, rng):
    rid, rows = cfg["run_id"], []
    for step in STEPS:
        t = step / 1000
        train = FLOOR[rid] + (10.8 - FLOOR[rid]) * math.exp(-SPEED[rid] * t) + rng.gauss(0, 0.02)
        val = train + 0.04 + rng.gauss(0, 0.015)
        gnorm = 0.9 + 2.0 * math.exp(-t) + abs(rng.gauss(0, 0.08))
        if rid == "run_3" and step > 7000:
            val += 0.0012 * (step - 7000) / 10  # mild late overfitting
        if rid == "run_4" and 300 <= step <= 1800:
            bump = math.exp(-((step - 700) / 250) ** 2)
            train += 2.4 * bump
            val += 2.5 * bump
            gnorm += 38 * bump
        if rid == "run_5" and step >= 2500:
            if step >= 3100:
                rows.append([step, "nan", "nan", "inf", f"{lr_at(step, cfg):.3e}"])
                continue
            blow = math.exp((step - 2500) / 150)
            train += 0.05 * blow
            val += 0.06 * blow
            gnorm += 3 * blow
        rows.append([step, f"{train:.4f}", f"{val:.4f}", f"{gnorm:.3f}", f"{lr_at(step, cfg):.3e}"])
    return rows


def main():
    rng = random.Random(7)
    (ROOT / "metrics").mkdir(exist_ok=True)
    with open(ROOT / "configs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RUNS[0].keys()))
        w.writeheader()
        w.writerows(RUNS)
    for cfg in RUNS:
        with open(ROOT / "metrics" / f"{cfg['run_id']}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["step", "train_loss", "val_loss", "grad_norm", "lr"])
            w.writerows(simulate(cfg, rng))
    print("wrote configs.csv and metrics/*.csv")


if __name__ == "__main__":
    main()
