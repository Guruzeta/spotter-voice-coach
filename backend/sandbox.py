"""One persistent Daytona sandbox per project (named tte-<slug>), holding the cloned repo.

The sandbox is reused across calls: the repo is cloned and indexed once, and every analysis,
file read and search the voice agent asks for runs there, not on the user's machine.
"""
import shlex
import threading
import time
import uuid
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona

from projects import DEMO_DIR, Project

PLOTS_DIR = Path(__file__).resolve().parent / "static" / "plots"
MAX_OUTPUT = 4000

PRELUDE = """\
import os, sys, warnings
warnings.filterwarnings("ignore")
os.chdir({root!r})
sys.path.insert(0, {root!r})
_FIGS = {figs!r}
os.makedirs(_FIGS, exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
pd.set_option("display.width", 160)
"""

# Any figure the agent's code leaves open gets saved, so the agent never manages file paths.
POSTLUDE = """
for _n in plt.get_fignums():
    plt.figure(_n).savefig(f"{_FIGS}/fig_{_n}.png", dpi=110, bbox_inches="tight")
plt.close("all")
"""

INDEX_SCRIPT = r'''
import os, json, csv
ROOT = {root!r}
SKIP = {{".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".ipynb_checkpoints", "dist", "build", ".idea", ".vscode", ".mypy_cache", ".pytest_cache", "site-packages"}}
DATA = (".csv", ".tsv", ".npy", ".npz", ".h5", ".hdf5", ".mat", ".pkl", ".parquet", ".json", ".txt", ".dat")
out, tree, notebooks, scripts, data, docs = [], [], [], [], [], []

def human(n):
    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024: return f"{{n:.0f}}{{u}}"
        n /= 1024
    return f"{{n:.0f}}TB"

for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = sorted(d for d in dirnames if d not in SKIP and not d.startswith("."))
    rel = os.path.relpath(dirpath, ROOT)
    depth = 0 if rel == "." else rel.count(os.sep) + 1
    if depth > 4: dirnames[:] = []; continue
    for f in sorted(filenames):
        if f.startswith("."): continue
        p = os.path.join(dirpath, f); r = os.path.normpath(os.path.join(rel, f))
        size = os.path.getsize(p)
        tree.append(f"{{r}} ({{human(size)}})")
        low = f.lower()
        if low.endswith(".ipynb"): notebooks.append((r, p))
        elif low.endswith((".py", ".jl", ".m", ".r", ".cpp", ".c", ".f90")): scripts.append((r, p))
        elif low.endswith((".md", ".rst", ".tex")): docs.append((r, p))
        elif low.endswith(DATA): data.append((r, p, size))

out.append(f"FILE TREE ({{len(tree)}} files; showing up to 150):")
out += ["- " + t for t in tree[:150]]

for name in ["README.md", "README.rst", "README.txt", "README", "readme.md"]:
    p = os.path.join(ROOT, name)
    if os.path.exists(p):
        out.append(f"\n=== {{name}} ===\n" + open(p, errors="ignore").read()[:3000]); break

for r, p in docs[:12]:
    if os.path.basename(r).lower().startswith("readme") and os.path.dirname(r) == "": continue
    txt = open(p, errors="ignore").read()
    out.append(f"\n=== doc {{r}} (first 600 chars) ===\n" + txt[:600])

for r, p in notebooks[:15]:
    try:
        nb = json.load(open(p))
        cells = nb.get("cells", [])
        md = [ "".join(c.get("source", ""))[:200].replace("\n", " ") for c in cells if c.get("cell_type") == "markdown"][:4]
        code = [ "".join(c.get("source", "")).split("\n")[0][:100] for c in cells if c.get("cell_type") == "code"][:6]
        out.append(f"\n=== notebook {{r}}: {{len(cells)}} cells ===\nmarkdown: " + " | ".join(md) + "\nfirst lines of code cells: " + " | ".join(code))
    except Exception as e:
        out.append(f"\n=== notebook {{r}}: unreadable ({{e}}) ===")

for r, p in scripts[:20]:
    lines = open(p, errors="ignore").read().splitlines()
    head = [l for l in lines[:40] if l.strip()][:8]
    defs = [l.strip()[:90] for l in lines if l.startswith(("def ", "class ", "function ", "subroutine "))][:10]
    out.append(f"\n=== script {{r}} ({{len(lines)}} lines) ===\n" + "\n".join(head) + ("\ndefinitions: " + "; ".join(defs) if defs else ""))

if data:
    out.append("\nDATA FILES:")
for r, p, size in data[:25]:
    info = f"- {{r}} ({{human(size)}})"
    if r.lower().endswith((".csv", ".tsv")):
        try:
            with open(p, errors="ignore") as f:
                info += " columns: " + f.readline().strip()[:200]
        except Exception:
            pass
    out.append(info)

print("\n".join(out)[:14000])
'''

READ_SCRIPT = r'''
import json, os
p = os.path.join({root!r}, {path!r})
start, n = {start}, {n}
if not os.path.exists(p):
    print(f"No such file: {path!r}. Use search_repo or the file tree.")
elif p.endswith(".ipynb"):
    nb = json.load(open(p))
    lines = []
    for i, c in enumerate(nb.get("cells", [])):
        lines.append(f"# --- cell {{i}} [{{c.get('cell_type')}}] ---")
        lines += "".join(c.get("source", "")).splitlines()
        for o in c.get("outputs", [])[:2]:
            txt = "".join(o.get("text", "") or o.get("data", {{}}).get("text/plain", ""))
            if txt: lines += ["# output: " + l for l in txt.splitlines()[:5]]
            if "image/png" in o.get("data", {{}}): lines.append("# output: [figure]")
    chunk = lines[start - 1:start - 1 + n]
    print(f"{{len(lines)}} lines total (notebook rendered as text); showing {{start}}-{{start + len(chunk) - 1}}")
    print("\n".join(chunk)[:12000])
else:
    lines = open(p, errors="ignore").read().splitlines()
    chunk = lines[start - 1:start - 1 + n]
    print(f"{{len(lines)}} lines total; showing {{start}}-{{start + len(chunk) - 1}}")
    print("\n".join(f"{{start + i}}: {{l}}" for i, l in enumerate(chunk))[:12000])
'''


def _started(sandbox) -> bool:
    return "started" in str(getattr(sandbox, "state", "")).lower()


class Workspace:
    def __init__(self):
        self._lock = threading.Lock()
        self._daytona = None
        self._cache: dict[str, tuple] = {}

    def _client(self):
        if self._daytona is None:
            self._daytona = Daytona()
        return self._daytona

    def get(self, project: Project, log=print):
        """Return (sandbox, repo_root, work_dir), reusing the project's sandbox across sessions."""
        with self._lock:
            if project.slug in self._cache:
                return self._cache[project.slug]
            t0 = time.time()
            d, name = self._client(), f"tte-{project.slug}"
            sandbox = None
            try:
                sandbox = d.get(name)
                if not _started(sandbox):
                    log(f"[sandbox] starting existing {name}")
                    sandbox.start(timeout=90)
            except Exception:
                sandbox = None
            if sandbox is None:
                log(f"[sandbox] creating {name}")
                sandbox = d.create(
                    CreateSandboxFromSnapshotParams(
                        name=name, language="python", auto_stop_interval=30, labels={"app": "talk-to-experiment", "project": project.slug}
                    ),
                    timeout=120,
                )
            work = sandbox.get_work_dir().rstrip("/")
            root = f"{work}/{project.slug}"
            marker = f"{work}/.tte_ready_{project.slug}"
            if sandbox.process.exec(f"test -f {marker} && echo yes").result.strip() != "yes":
                self._populate(sandbox, root, project)
                sandbox.process.exec(f"touch {marker}")
            self._cache[project.slug] = (sandbox, root, work)
            log(f"[sandbox] {name} ready in {time.time() - t0:.1f}s, repo at {root}")
            return self._cache[project.slug]

    def _populate(self, sandbox, root, project: Project):
        if project.source == "demo":
            files = [p for p in DEMO_DIR.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
            dirs = sorted({str(Path(root) / p.relative_to(DEMO_DIR).parent) for p in files})
            sandbox.process.exec("mkdir -p " + " ".join(shlex.quote(d) for d in dirs))
            for p in files:
                sandbox.fs.upload_file(p.read_bytes(), f"{root}/{p.relative_to(DEMO_DIR)}")
            return
        r = sandbox.process.exec(f"rm -rf {shlex.quote(root)} && git clone --depth 1 {shlex.quote(project.source)} {shlex.quote(root)}", timeout=240)
        if r.exit_code != 0:
            raise RuntimeError(f"git clone failed: {(r.result or '')[-400:]}")
        # Best effort: install the repo's own requirements so its code can be imported/run.
        sandbox.process.exec(f"cd {shlex.quote(root)} && [ -f requirements.txt ] && pip install -q -r requirements.txt || true", timeout=240)

    def index(self, project: Project) -> str:
        sandbox, root, _ = self.get(project)
        resp = sandbox.process.code_run(INDEX_SCRIPT.format(root=root), timeout=90)
        text = resp.result or ""
        project.index_path.write_text(text)
        return text

    def run(self, project: Project, code: str) -> dict:
        sandbox, root, work = self.get(project)
        figs = f"{work}/.tte_figs"
        t0 = time.time()
        resp = sandbox.process.code_run(PRELUDE.format(root=root, figs=figs) + "\n" + code + "\n" + POSTLUDE, timeout=120)
        plots = []
        try:
            infos = sandbox.fs.list_files(figs)
        except Exception:
            infos = []
        for info in infos:
            if not info.name.endswith(".png"):
                continue
            remote = f"{figs}/{info.name}"
            name = f"{uuid.uuid4().hex[:10]}.png"
            (PLOTS_DIR / name).write_bytes(sandbox.fs.download_file(remote))
            sandbox.fs.delete_file(remote)
            plots.append(f"/plots/{name}")
        output = resp.result or ""
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n...[truncated]"
        return {"exit_code": resp.exit_code, "output": output, "plots": plots, "sandbox_id": sandbox.id, "seconds": round(time.time() - t0, 2)}

    def read_file(self, project: Project, path: str, start: int = 1, n: int = 150) -> str:
        sandbox, root, _ = self.get(project)
        start, n = max(1, int(start)), max(10, min(int(n), 300))
        resp = sandbox.process.code_run(READ_SCRIPT.format(root=root, path=path.lstrip("/"), start=start, n=n), timeout=60)
        return resp.result or "(empty)"

    def search(self, project: Project, pattern: str) -> str:
        sandbox, root, _ = self.get(project)
        script = (
            f"grep -rnIi --exclude-dir=.git --exclude-dir=node_modules --exclude='*.ipynb' -m 5 -e {shlex.quote(pattern)} . | cut -c1-200 | head -40;"
            f" grep -rlIi --include='*.ipynb' -e {shlex.quote(pattern)} . | head -10 | sed 's/^/[notebook match] /'"
        )
        resp = sandbox.process.exec(f"bash -c {shlex.quote(script)}", cwd=root, timeout=60)
        return (resp.result or "").strip() or "No matches."
