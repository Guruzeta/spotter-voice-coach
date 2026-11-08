"""Projects = repos Sam has been pointed at. Each keeps persistent state across calls:

projects/<slug>/meta.json   source + title
projects/<slug>/index.txt   repo index built in the Daytona sandbox (tree, README, notebooks, data)
projects/<slug>/MEMORY.md   findings, decisions and preferences Sam chose to remember
projects/<slug>/TODO.md     open questions
"""
import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = REPO_ROOT / "projects"
DEMO_DIR = REPO_ROOT / "demo_experiment"
EMPTY_TODO = "# Open questions\n\n"


@dataclass
class Project:
    slug: str
    source: str  # "demo" or a git URL
    title: str

    @property
    def dir(self) -> Path:
        return PROJECTS_DIR / self.slug

    @property
    def todo_path(self) -> Path:
        return self.dir / "TODO.md"

    @property
    def memory_path(self) -> Path:
        return self.dir / "MEMORY.md"

    @property
    def index_path(self) -> Path:
        return self.dir / "index.txt"

    def todo_seed(self) -> str:
        seed = DEMO_DIR / "TODO.md"
        return seed.read_text() if self.source == "demo" and seed.exists() else EMPTY_TODO


def normalize(source: str) -> tuple[str, str, str]:
    """Returns (slug, source, title) for 'demo', 'owner/repo' or a GitHub/git URL."""
    s = source.strip().rstrip("/")
    if not s or s.lower() == "demo":
        return "demo", "demo", "Spring-mass integrators (demo)"
    if re.fullmatch(r"[\w.-]+/[\w.-]+", s):
        s = f"https://github.com/{s}"
    s = re.sub(r"\.git$", "", s)
    m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+)", s)
    if m:
        owner, repo = m.groups()
        return re.sub(r"[^a-z0-9-]+", "-", f"{owner}-{repo}".lower()), f"https://github.com/{owner}/{repo}.git", repo
    name = s.split("/")[-1]
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()), s, name


_lock = threading.Lock()
_active: Project | None = None


def load_or_create(source: str) -> Project:
    slug, src, title = normalize(source)
    p = Project(slug, src, title)
    p.dir.mkdir(parents=True, exist_ok=True)
    meta = p.dir / "meta.json"
    if not meta.exists():
        meta.write_text(json.dumps(asdict(p), indent=2))
    if not p.todo_path.exists():
        p.todo_path.write_text(p.todo_seed())
    if not p.memory_path.exists():
        p.memory_path.write_text("# Project memory\n\n")
    return p


ACTIVE_FILE = PROJECTS_DIR / "active.txt"  # survives backend restarts


def set_active(p: Project):
    global _active
    with _lock:
        _active = p
        ACTIVE_FILE.write_text(p.source)


def active() -> Project:
    global _active
    with _lock:
        if _active is None:
            source = ACTIVE_FILE.read_text().strip() if ACTIVE_FILE.exists() else "demo"
            _active = load_or_create(source)
        return _active


def list_projects() -> list[dict]:
    out = []
    for meta in sorted(PROJECTS_DIR.glob("*/meta.json"), key=lambda m: m.stat().st_mtime, reverse=True):
        out.append(json.loads(meta.read_text()))
    return out


def remember(p: Project, note: str) -> str:
    note = note.replace("\n", " ").strip()
    with p.memory_path.open("a") as f:
        f.write(f"- [{datetime.now():%Y-%m-%d %H:%M}] {note}\n")
    return memory_text(p)


def memory_text(p: Project) -> str:
    lines = [l for l in p.memory_path.read_text().splitlines() if l.startswith("- ")] if p.memory_path.exists() else []
    return "\n".join(lines[-40:]) or "(nothing yet — this is the first session on this project)"
