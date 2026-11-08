"""One warm Daytona sandbox per backend process, holding a copy of the experiment folder.

Every analysis the voice agent asks for runs here, not on the user's machine.
"""
import threading
import time
import uuid
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent / "demo_experiment"
PLOTS_DIR = Path(__file__).resolve().parent / "static" / "plots"
MAX_OUTPUT = 4000

PRELUDE = """\
import os, warnings
warnings.filterwarnings("ignore")
os.chdir({root!r})
os.makedirs("figs", exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
pd.set_option("display.width", 160)
"""

# Any figure the agent's code leaves open gets saved, so the agent never has to manage file paths.
POSTLUDE = """
for _n in plt.get_fignums():
    plt.figure(_n).savefig(f"figs/fig_{_n}.png", dpi=110, bbox_inches="tight")
plt.close("all")
"""


class ExperimentSandbox:
    def __init__(self):
        self._lock = threading.Lock()
        self._daytona = None
        self._sandbox = None
        self._root = None

    def _upload_experiment(self, sandbox, root):
        files = [p for p in EXPERIMENT_DIR.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        dirs = sorted({str(Path(root) / p.relative_to(EXPERIMENT_DIR).parent) for p in files})
        sandbox.process.exec("mkdir -p " + " ".join(f"'{d}'" for d in dirs + [f"{root}/figs"]))
        for p in files:
            sandbox.fs.upload_file(p.read_bytes(), f"{root}/{p.relative_to(EXPERIMENT_DIR)}")

    def get(self):
        with self._lock:
            if self._sandbox is None:
                t0 = time.time()
                self._daytona = Daytona()
                sandbox = self._daytona.create(
                    CreateSandboxFromSnapshotParams(
                        language="python",
                        auto_stop_interval=30,
                        labels={"app": "talk-to-experiment"},
                    )
                )
                root = f"{sandbox.get_work_dir().rstrip('/')}/experiment"
                self._upload_experiment(sandbox, root)
                self._sandbox, self._root = sandbox, root
                print(f"[sandbox] ready {sandbox.id} in {time.time() - t0:.1f}s, experiment at {root}")
            return self._sandbox, self._root

    def run(self, code: str) -> dict:
        sandbox, root = self.get()
        t0 = time.time()
        resp = sandbox.process.code_run(PRELUDE.format(root=root) + "\n" + code + "\n" + POSTLUDE, timeout=90)
        plots = []
        for info in sandbox.fs.list_files(f"{root}/figs"):
            if not info.name.endswith(".png"):
                continue
            remote = f"{root}/figs/{info.name}"
            name = f"{uuid.uuid4().hex[:10]}.png"
            (PLOTS_DIR / name).write_bytes(sandbox.fs.download_file(remote))
            sandbox.fs.delete_file(remote)
            plots.append(f"/plots/{name}")
        output = resp.result or ""
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n...[truncated]"
        return {
            "exit_code": resp.exit_code,
            "output": output,
            "plots": plots,
            "sandbox_id": sandbox.id,
            "seconds": round(time.time() - t0, 2),
        }

    def close(self):
        with self._lock:
            if self._sandbox is not None:
                try:
                    self._sandbox.delete()
                except Exception as e:  # noqa: BLE001
                    print(f"[sandbox] delete failed: {e}")
                self._sandbox = None


def experiment_overview() -> str:
    """Text snapshot of the experiment folder the agent reads at the start of a session."""
    parts = []
    files = sorted(p.relative_to(EXPERIMENT_DIR).as_posix() for p in EXPERIMENT_DIR.rglob("*") if p.is_file())
    parts.append("FILES:\n" + "\n".join(f"- {f}" for f in files if not f.endswith("make_data.py")))
    for name in ["NOTES.md", "configs.csv"]:
        p = EXPERIMENT_DIR / name
        if p.exists():
            parts.append(f"=== {name} ===\n{p.read_text()}")
    sample = EXPERIMENT_DIR / "metrics" / "run_1.csv"
    if sample.exists():
        head = "\n".join(sample.read_text().splitlines()[:4])
        parts.append(f"=== metrics/run_1.csv (first rows; all runs share these columns) ===\n{head}")
    train = EXPERIMENT_DIR / "train.py"
    if train.exists():
        parts.append(f"=== train.py ===\n{train.read_text()}")
    return "\n\n".join(parts)
