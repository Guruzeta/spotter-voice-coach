"""Training analysis that runs in a Daytona sandbox: estimated maxes, trends, fatigue, load prescription, plans.

The voice agent never does arithmetic itself; every number it says comes from code run here.
"""
import json
import threading
import time
import uuid
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona

PLOTS_DIR = Path(__file__).resolve().parent / "static" / "plots"
SANDBOX_NAME = "spotter-coach"

COMMON = r'''
import io, json, os, math
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
os.makedirs("/tmp/figs", exist_ok=True)
hist = pd.read_csv(io.StringIO({history!r}))
today = pd.read_csv(io.StringIO({today!r}))
TODAY = {today_date!r}

def e1rm(w, reps, rpe):
    # Epley with reps-in-reserve: a set of r reps at RPE x ~ (r + 10 - x) reps to failure
    return w * (1 + (reps + (10 - rpe)) / 30.0)

def load_for(e, reps, rpe):
    return e / (1 + (reps + (10 - rpe)) / 30.0)

def rnd(w, step=5):
    return float(step * round(w / step))

for df in (hist, today):
    if len(df):
        df["e1rm"] = e1rm(df.weight_lb, df.reps, df.rpe)
'''

NEXT_SET = COMMON + r'''
ex, target_reps, target_rpe = {exercise!r}, {reps}, {rpe}
h = hist[hist.exercise == ex]
t = today[today.exercise == ex]
sessions = h.groupby("date").e1rm.max().sort_index()
out = {{"exercise": ex}}
if len(sessions):
    x = np.arange(len(sessions))
    slope = np.polyfit(x, sessions.values, 1)[0] if len(sessions) > 1 else 0.0
    out["last_session_e1rm"] = round(float(sessions.iloc[-1]), 1)
    out["trend_lb_per_session"] = round(float(slope), 1)
    recent = sessions.iloc[-3:]
    out["plateau"] = bool(len(recent) == 3 and recent.max() - recent.min() < 0.02 * recent.mean())
if len(t):
    best = float(t.e1rm.max()); last = float(t.e1rm.iloc[-1])
    out["today_best_e1rm"] = round(best, 1)
    out["fatigue_drop_pct"] = round(100 * (best - last) / best, 1)
    base = best
    if len(sessions):
        out["vs_last_session_pct"] = round(100 * (best / sessions.iloc[-1] - 1), 1)
else:
    base = float(sessions.iloc[-1]) if len(sessions) else None
if base is None:
    out["prescription"] = None; out["note"] = "No data for this lift yet; start light and log a set."
else:
    w = load_for(base, target_reps, target_rpe)
    if out.get("fatigue_drop_pct", 0) > 7:
        w *= 0.95; out["note"] = "Fatigue detected (performance dropped over 7% since your best set): load reduced 5%."
    step = 5 if w >= 50 else 2.5
    out["prescription"] = {{"weight_lb": rnd(w, step), "reps": target_reps, "rpe": target_rpe}}
    fig, ax = plt.subplots(figsize=(6, 3.2))
    if len(sessions):
        ax.plot(pd.to_datetime(sessions.index), sessions.values, "o-", label="best estimated max per session")
    if len(t):
        ax.plot([pd.to_datetime(TODAY)], [best], "r*", ms=16, label="today")
    ax.set_title(f"{{ex}}: estimated 1-rep max (lb)"); ax.legend(loc="lower right", fontsize=8); ax.grid(alpha=.3)
    fig.autofmt_xdate(); fig.savefig("/tmp/figs/next.png", dpi=110, bbox_inches="tight")
print("RESULT:" + json.dumps(out))
'''

FINISH = COMMON + r'''
out = {{"exercises": []}}
plan = []
fig, ax = plt.subplots(figsize=(6.4, 3.4))
for ex, t in today.groupby("exercise"):
    h = hist[hist.exercise == ex]
    prev_best = float(h.e1rm.max()) if len(h) else 0
    best = float(t.e1rm.max())
    vol = float((t.weight_lb * t.reps).sum())
    sessions = h.groupby("date").e1rm.max().sort_index()
    pr = best > prev_best
    nxt = best * (1.01 if not pr else 1.02)
    step = 5 if nxt >= 80 else 2.5
    target = {{"sets": 3, "reps": 5, "rpe": 8, "weight_lb": rnd(load_for(nxt, 5, 8), step)}}
    out["exercises"].append({{"exercise": ex, "sets": int(len(t)), "volume_lb": vol, "today_best_e1rm": round(best, 1),
                             "previous_best_e1rm": round(prev_best, 1), "personal_record": pr, "next_session": target}})
    plan.append(f"| {{ex}} | {{target['sets']}} x {{target['reps']}} @ RPE {{target['rpe']}} | {{target['weight_lb']:g}} lb |")
    if len(sessions):
        s = pd.concat([sessions, pd.Series({{TODAY: best}})])
        ax.plot(pd.to_datetime(s.index), s.values / s.values[0] * 100, "o-", label=ex)
ax.set_title("Strength trend (estimated max, % of 8 weeks ago)"); ax.grid(alpha=.3); ax.legend(fontsize=8)
fig.autofmt_xdate(); fig.savefig("/tmp/figs/progress.png", dpi=110, bbox_inches="tight")
out["total_volume_lb"] = float(sum(e["volume_lb"] for e in out["exercises"]))
out["plan_table"] = "| Exercise | Target | Weight |\n|---|---|---|\n" + "\n".join(plan)
print("RESULT:" + json.dumps(out))
'''


class Coach:
    def __init__(self):
        self._lock = threading.Lock()
        self._sandbox = None

    def sandbox(self):
        with self._lock:
            if self._sandbox is None:
                d = Daytona()
                try:
                    sb = d.get(SANDBOX_NAME)
                    if "started" not in str(getattr(sb, "state", "")).lower():
                        sb.start(timeout=90)
                except Exception:
                    sb = d.create(CreateSandboxFromSnapshotParams(name=SANDBOX_NAME, language="python", auto_stop_interval=30), timeout=120)
                self._sandbox = sb
            return self._sandbox

    def _run(self, script: str) -> dict:
        sb = self.sandbox()
        t0 = time.time()
        resp = sb.process.code_run(script, timeout=60)
        text = resp.result or ""
        line = next((l for l in text.splitlines() if l.startswith("RESULT:")), None)
        if resp.exit_code != 0 or line is None:
            return {"error": text[-800:] or f"exit {resp.exit_code}"}
        out = json.loads(line[len("RESULT:"):])
        plots = []
        for info in sb.fs.list_files("/tmp/figs"):
            if info.name.endswith(".png"):
                name = f"{uuid.uuid4().hex[:10]}.png"
                (PLOTS_DIR / name).write_bytes(sb.fs.download_file(f"/tmp/figs/{info.name}"))
                sb.fs.delete_file(f"/tmp/figs/{info.name}")
                plots.append(f"/plots/{name}")
        out["plots"] = plots
        out["sandbox_seconds"] = round(time.time() - t0, 2)
        return out

    def next_set(self, history_csv, today_csv, today_date, exercise, reps, rpe):
        return self._run(NEXT_SET.format(history=history_csv, today=today_csv, today_date=today_date, exercise=exercise, reps=int(reps), rpe=float(rpe)))

    def finish(self, history_csv, today_csv, today_date):
        return self._run(FINISH.format(history=history_csv, today=today_csv, today_date=today_date))
