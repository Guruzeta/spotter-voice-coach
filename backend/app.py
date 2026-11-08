import os
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import projects
import todos
from sandbox import PLOTS_DIR, Workspace

load_dotenv(find_dotenv(usecwd=True))

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
ELEVEN_API = "https://api.elevenlabs.io/v1"

PLOTS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
projects.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
workspace = Workspace()
app = FastAPI()

MODES = {
    "todo": "SESSION MODE: TODO — work through the researcher's to-do list together (see 'Mode: to-do list').",
    "walkthrough": "SESSION MODE: WALKTHROUGH — present the whole project section by section like a grad student to an advisor (see 'Mode: walkthrough').",
}


# ---------- voice session ----------
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
        r2 = await client.get(f"{ELEVEN_API}/convai/conversation/get-signed-url", params={"agent_id": agent_id}, headers=headers)
        if r2.status_code == 200:
            return {"signed_url": r2.json()["signed_url"]}
    raise HTTPException(502, f"ElevenLabs auth failed: {r.status_code} {r.text[:200]} / {r2.status_code} {r2.text[:200]}")


# ---------- projects ----------
def project_info(p):
    return {
        "slug": p.slug,
        "title": p.title,
        "source": p.source,
        "indexed": p.index_path.exists(),
        "memory_items": projects.memory_text(p).count("\n- ") + (1 if projects.memory_text(p).startswith("- ") else 0),
        "todos": todos.list_todos(p),
    }


@app.get("/api/project")
def get_project():
    return {"active": project_info(projects.active()), "recent": projects.list_projects()}


class ProjectRequest(BaseModel):
    source: str


@app.post("/api/project")
def open_project(req: ProjectRequest):
    """Point Sam at a repo: clone it into its own persistent Daytona sandbox and index it (first time only)."""
    p = projects.load_or_create(req.source)
    try:
        workspace.get(p)
        if not p.index_path.exists():
            workspace.index(p)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not open {p.source}: {e}")
    projects.set_active(p)
    return {"active": project_info(p), "recent": projects.list_projects()}


@app.post("/api/project/reindex")
def reindex():
    p = projects.active()
    workspace.index(p)
    return {"active": project_info(p)}


@app.post("/api/warmup")
def warmup():
    threading.Thread(target=workspace.get, args=(projects.active(),), daemon=True).start()
    return {"ok": True}


# ---------- what the agent reads at the start of a call ----------
@app.get("/api/experiment")
def experiment(mode: str = "todo"):
    p = projects.active()
    if not p.index_path.exists():
        workspace.index(p)
    items = todos.list_todos(p)
    overview = "\n\n".join(
        [
            MODES.get(mode, MODES["todo"]),
            f"PROJECT: {p.title}  (source: {p.source})",
            "=== PROJECT MEMORY (from previous sessions; oldest first) ===\n" + projects.memory_text(p),
            "=== RESEARCHER'S TO-DO LIST (id. [status] question) ===\n" + todos.as_text(items),
            "=== REPO INDEX ===\n" + p.index_path.read_text(),
        ]
    )
    return {"overview": overview, "todos": items, "project": project_info(p)}


# ---------- agent tools ----------
class RunRequest(BaseModel):
    code: str
    purpose: str = ""


@app.post("/api/run")
def run(req: RunRequest):
    print(f"[run] {req.purpose}")
    try:
        return workspace.run(projects.active(), req.code)
    except Exception as e:  # noqa: BLE001 - surface any sandbox failure to the agent
        return {"exit_code": -1, "output": f"Sandbox error: {e}", "plots": []}


class ReadRequest(BaseModel):
    path: str
    start_line: int = 1
    max_lines: int = 150


@app.post("/api/read")
def read(req: ReadRequest):
    try:
        return {"content": workspace.read_file(projects.active(), req.path, req.start_line, req.max_lines)}
    except Exception as e:  # noqa: BLE001
        return {"content": f"Read error: {e}"}


class SearchRequest(BaseModel):
    pattern: str


@app.post("/api/search")
def search(req: SearchRequest):
    try:
        return {"content": workspace.search(projects.active(), req.pattern)}
    except Exception as e:  # noqa: BLE001
        return {"content": f"Search error: {e}"}


class RememberRequest(BaseModel):
    note: str


@app.post("/api/remember")
def remember(req: RememberRequest):
    p = projects.active()
    projects.remember(p, req.note)
    return {"ok": True, "memory": projects.memory_text(p)}


@app.get("/api/todos")
def get_todos():
    return {"todos": todos.list_todos(projects.active())}


class TodoUpdate(BaseModel):
    id: int
    status: str
    finding: str = ""


@app.post("/api/todos/update")
def update_todo(req: TodoUpdate):
    p = projects.active()
    try:
        items = todos.update_todo(p, req.id, req.status, req.finding)
    except ValueError as e:
        return {"error": str(e), "todos": todos.list_todos(p)}
    return {"todos": items}


class TodoAdd(BaseModel):
    text: str


@app.post("/api/todos/add")
def add_todo(req: TodoAdd):
    return {"todos": todos.add_todo(projects.active(), req.text)}


@app.post("/api/todos/reset")
def reset_todos():
    return {"todos": todos.reset_todos(projects.active())}


class ReportRequest(BaseModel):
    title: str
    markdown: str
    plots: list[str] = []


@app.post("/api/report")
def report(req: ReportRequest):
    p = projects.active()
    slug = re.sub(r"[^a-z0-9]+", "-", req.title.lower()).strip("-")[:50] or "report"
    folder = REPORTS_DIR / p.slug / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}"
    folder.mkdir(parents=True)
    body = req.markdown + "\n\n## To-do status\n\n" + todos.as_markdown(todos.list_todos(p))
    images = []
    for url in req.plots:
        src = PLOTS_DIR / Path(url).name
        if src.exists():
            shutil.copy(src, folder / src.name)
            images.append(src.name)
    if images:
        body += "\n\n## Figures\n\n" + "\n\n".join(f"![]({name})" for name in images)
    (folder / "report.md").write_text(f"# {req.title}\n\n_Project: {p.title} ({p.source})_\n\n{body}\n")
    projects.remember(p, f"Saved report '{req.title}' at {folder.relative_to(REPO_ROOT).as_posix()}/report.md")
    rel = folder.relative_to(REPO_ROOT).as_posix()
    return {"path": f"{rel}/report.md", "url": f"/{rel}/report.md"}


app.mount("/plots", StaticFiles(directory=PLOTS_DIR), name="plots")
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
