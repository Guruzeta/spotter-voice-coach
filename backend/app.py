import csv
import io
import os
import threading
from datetime import date, datetime
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coach import PLOTS_DIR, Coach

load_dotenv(find_dotenv(usecwd=True))

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "history.csv"
SESSIONS = DATA / "sessions"
PLANS = ROOT / "plans"
ELEVEN_API = "https://api.elevenlabs.io/v1"
FIELDS = ["date", "exercise", "weight_lb", "reps", "rpe"]

for d in (PLOTS_DIR, SESSIONS, PLANS):
    d.mkdir(parents=True, exist_ok=True)

coach = Coach()
app = FastAPI()
lock = threading.Lock()
today_sets: list[dict] = []  # the workout in progress

ALIASES = {
    "bench": "bench press", "benchpress": "bench press", "bench presses": "bench press",
    "squats": "squat", "back squat": "squat", "deadlifts": "deadlift", "dead lift": "deadlift",
    "goblet squats": "goblet squat", "goblet": "goblet squat",
}


def norm(ex: str) -> str:
    e = " ".join(ex.lower().strip().split())
    return ALIASES.get(e, e)


def to_csv(rows) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def state():
    with lock:
        sets = [{"n": i + 1, **s} for i, s in enumerate(today_sets)]
    return {"sets": sets}


@app.get("/api/session")
async def session():
    key, agent_id = os.getenv("ELEVENLABS_API_KEY"), os.getenv("ELEVENLABS_AGENT_ID")
    if not key or not agent_id:
        raise HTTPException(500, "Set ELEVENLABS_API_KEY and run setup_agent.py first")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{ELEVEN_API}/convai/conversation/token", params={"agent_id": agent_id}, headers={"xi-api-key": key})
    if r.status_code != 200:
        raise HTTPException(502, f"ElevenLabs auth failed: {r.status_code} {r.text[:200]}")
    return {"conversation_token": r.json()["token"]}


@app.post("/api/warmup")
def warmup():
    threading.Thread(target=coach.sandbox, daemon=True).start()
    return {"ok": True}


@app.get("/api/state")
def get_state():
    return state()


class SetIn(BaseModel):
    exercise: str
    weight_lb: float
    reps: int
    rpe: float = 8


@app.post("/api/log_set")
def log_set(s: SetIn):
    row = {"date": date.today().isoformat(), "exercise": norm(s.exercise), "weight_lb": s.weight_lb, "reps": s.reps, "rpe": s.rpe}
    with lock:
        today_sets.append(row)
        n = len(today_sets)
    est = s.weight_lb * (1 + (s.reps + (10 - s.rpe)) / 30)
    return {"set_number": n, "logged": row, "estimated_max_lb": round(est, 1), **state()}


class EditIn(BaseModel):
    set_number: int
    exercise: str | None = None
    weight_lb: float | None = None
    reps: int | None = None
    rpe: float | None = None


@app.post("/api/edit_set")
def edit_set(e: EditIn):
    with lock:
        if not 1 <= e.set_number <= len(today_sets):
            return {"error": f"No set {e.set_number}; there are {len(today_sets)} sets today.", **state()}
        row = today_sets[e.set_number - 1]
        for k in ("weight_lb", "reps", "rpe"):
            if getattr(e, k) is not None:
                row[k] = getattr(e, k)
        if e.exercise:
            row["exercise"] = norm(e.exercise)
    return {"edited": e.set_number, **state()}


@app.post("/api/delete_set")
def delete_set(e: EditIn):
    with lock:
        if not 1 <= e.set_number <= len(today_sets):
            return {"error": f"No set {e.set_number}.", **state()}
        today_sets.pop(e.set_number - 1)
    return {"deleted": e.set_number, **state()}


class NextIn(BaseModel):
    exercise: str
    reps: int = 5
    rpe: float = 8


@app.post("/api/next_set")
def next_set(n: NextIn):
    with lock:
        today_csv = to_csv(today_sets)
    try:
        return coach.next_set(HISTORY.read_text(), today_csv, date.today().isoformat(), norm(n.exercise), n.reps, n.rpe)
    except Exception as e:  # noqa: BLE001
        return {"error": f"Sandbox error: {e}"}


@app.post("/api/finish")
def finish():
    with lock:
        rows = list(today_sets)
    if not rows:
        return {"error": "No sets logged yet."}
    try:
        result = coach.finish(HISTORY.read_text(), to_csv(rows), date.today().isoformat())
    except Exception as e:  # noqa: BLE001
        return {"error": f"Sandbox error: {e}"}
    if "error" in result:
        return result
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    (SESSIONS / f"{stamp}.csv").write_text(to_csv(rows))
    with HISTORY.open("a", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore").writerows(rows)
    lines = [f"# Next session plan (written {stamp})", "", result["plan_table"], "", "## Today", ""]
    for e in result["exercises"]:
        pr = " **PR!**" if e["personal_record"] else ""
        lines.append(f"- {e['exercise']}: {e['sets']} sets, {e['volume_lb']:.0f} lb volume, best est. max {e['today_best_e1rm']} lb (previous best {e['previous_best_e1rm']}){pr}")
    plan_path = PLANS / "next-session.md"
    plan_path.write_text("\n".join(lines) + "\n")
    with lock:
        today_sets.clear()
    result["saved"] = {"session": f"data/sessions/{stamp}.csv", "plan": "plans/next-session.md"}
    return result


@app.post("/api/reset")
def reset():
    with lock:
        today_sets.clear()
    return state()


app.mount("/plots", StaticFiles(directory=PLOTS_DIR), name="plots")
