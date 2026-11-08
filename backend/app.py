import os
import re
import shutil
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import todos
from sandbox import PLOTS_DIR, ExperimentSandbox, experiment_overview

load_dotenv(find_dotenv(usecwd=True))

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
ELEVEN_API = "https://api.elevenlabs.io/v1"

PLOTS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
sandbox = ExperimentSandbox()


@asynccontextmanager
async def lifespan(_app):
    yield
    sandbox.close()


app = FastAPI(lifespan=lifespan)


@app.get("/api/session")
async def session():
    """Short-lived credential so the browser can talk to the private agent without seeing the API key."""
    key, agent_id = os.getenv("ELEVENLABS_API_KEY"), os.getenv("ELEVENLABS_AGENT_ID")
    if not key or not agent_id:
        raise HTTPException(500, "Set ELEVENLABS_API_KEY and run setup_agent.py first")
    headers = {"xi-api-key": key}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{ELEVEN_API}/convai/conversation/token", params={"agent_id": agent_id}, headers=headers)
        if r.status_code == 200 and r.json().get("token"):
            return {"conversation_token": r.json()["token"]}
        r2 = await client.get(
            f"{ELEVEN_API}/convai/conversation/get-signed-url", params={"agent_id": agent_id}, headers=headers
        )
        if r2.status_code == 200:
            return {"signed_url": r2.json()["signed_url"]}
    raise HTTPException(502, f"ElevenLabs auth failed: {r.status_code} {r.text[:200]} / {r2.status_code} {r2.text[:200]}")


@app.post("/api/warmup")
def warmup():
    threading.Thread(target=sandbox.get, daemon=True).start()
    return {"ok": True}


MODES = {
    "todo": "SESSION MODE: TODO — work through the researcher's to-do list together (see 'Mode: to-do list').",
    "walkthrough": "SESSION MODE: WALKTHROUGH — present the whole experiment section by section like a grad student to an advisor (see 'Mode: walkthrough').",
}


@app.get("/api/experiment")
def experiment(mode: str = "todo"):
    return {
        "overview": MODES.get(mode, MODES["todo"])
        + "\n\n"
        + experiment_overview()
        + "\n\n=== RESEARCHER'S TO-DO LIST (id. [status] question) ===\n"
        + todos.as_text(),
        "todos": todos.list_todos(),
    }


@app.get("/api/todos")
def get_todos():
    return {"todos": todos.list_todos()}


class TodoUpdate(BaseModel):
    id: int
    status: str
    finding: str = ""


@app.post("/api/todos/update")
def update_todo(req: TodoUpdate):
    try:
        items = todos.update_todo(req.id, req.status, req.finding)
    except ValueError as e:
        return {"error": str(e), "todos": todos.list_todos()}
    return {"todos": items}


class TodoAdd(BaseModel):
    text: str


@app.post("/api/todos/add")
def add_todo(req: TodoAdd):
    return {"todos": todos.add_todo(req.text)}


@app.post("/api/todos/reset")
def reset_todos():
    return {"todos": todos.reset_todos()}


class RunRequest(BaseModel):
    code: str
    purpose: str = ""


@app.post("/api/run")
def run(req: RunRequest):
    print(f"[run] {req.purpose}")
    try:
        return sandbox.run(req.code)
    except Exception as e:  # noqa: BLE001 - surface any sandbox failure to the agent
        return {"exit_code": -1, "output": f"Sandbox error: {e}", "plots": []}


class ReportRequest(BaseModel):
    title: str
    markdown: str
    plots: list[str] = []


@app.post("/api/report")
def report(req: ReportRequest):
    slug = re.sub(r"[^a-z0-9]+", "-", req.title.lower()).strip("-")[:50] or "report"
    folder = REPORTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}"
    folder.mkdir(parents=True)
    body = req.markdown
    images = []
    for url in req.plots:
        src = PLOTS_DIR / Path(url).name
        if src.exists():
            shutil.copy(src, folder / src.name)
            images.append(src.name)
    body += "\n\n## To-do status\n\n" + todos.as_markdown()
    if images:
        body += "\n\n## Figures\n\n" + "\n\n".join(f"![]({name})" for name in images)
    (folder / "report.md").write_text(f"# {req.title}\n\n{body}\n")
    rel = folder.relative_to(REPO_ROOT).as_posix()
    return {"path": f"{rel}/report.md", "url": f"/{rel}/report.md"}


app.mount("/plots", StaticFiles(directory=PLOTS_DIR), name="plots")
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
