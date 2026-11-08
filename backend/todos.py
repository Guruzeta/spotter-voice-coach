"""The researcher's open questions, stored as a markdown checklist in the experiment folder.

    - [ ] open        - [~] in progress        - [x] done        - [-] skipped
    Done items carry their verified finding:  - [x] question — Finding: ...
"""
import re
import threading

from sandbox import EXPERIMENT_DIR

TODO_PATH = EXPERIMENT_DIR / "TODO.md"
MARKS = {" ": "open", "~": "in_progress", "x": "done", "-": "skipped"}
SYMBOL = {v: k for k, v in MARKS.items()}
LINE = re.compile(r"^- \[([ ~x\-])\] (.*?)(?: — Finding: (.*))?$")

_lock = threading.Lock()
_original = TODO_PATH.read_text() if TODO_PATH.exists() else "# Open questions\n\n"


def _read():
    header, items = [], []
    for line in TODO_PATH.read_text().splitlines() if TODO_PATH.exists() else []:
        m = LINE.match(line.strip())
        if m:
            items.append({"status": MARKS[m.group(1)], "text": m.group(2).strip(), "finding": (m.group(3) or "").strip()})
        elif not items:
            header.append(line)
    return header, items


def _write(header, items):
    lines = [*header]
    if lines and lines[-1].strip():
        lines.append("")
    for it in items:
        line = f"- [{SYMBOL[it['status']]}] {it['text']}"
        if it["finding"]:
            line += f" — Finding: {it['finding']}"
        lines.append(line)
    TODO_PATH.write_text("\n".join(lines) + "\n")


def list_todos():
    with _lock:
        _, items = _read()
    return [{"id": i + 1, **it} for i, it in enumerate(items)]


def update_todo(todo_id: int, status: str, finding: str = ""):
    if status not in SYMBOL:
        raise ValueError(f"status must be one of {list(SYMBOL)}")
    with _lock:
        header, items = _read()
        if not 1 <= todo_id <= len(items):
            raise ValueError(f"no to-do with id {todo_id}; ids are 1..{len(items)}")
        if status == "in_progress":  # only one thing in progress at a time
            for it in items:
                if it["status"] == "in_progress":
                    it["status"] = "open"
        items[todo_id - 1]["status"] = status
        if finding:
            items[todo_id - 1]["finding"] = finding.replace("\n", " ").strip()
        _write(header, items)
    return list_todos()


def add_todo(text: str):
    with _lock:
        header, items = _read()
        items.append({"status": "open", "text": text.replace("\n", " ").strip(), "finding": ""})
        _write(header, items)
    return list_todos()


def reset_todos():
    with _lock:
        TODO_PATH.write_text(_original)
    return list_todos()


def as_text(todos=None):
    todos = list_todos() if todos is None else todos
    if not todos:
        return "No to-dos."
    out = []
    for t in todos:
        line = f"{t['id']}. [{t['status']}] {t['text']}"
        if t["finding"]:
            line += f" (finding: {t['finding']})"
        out.append(line)
    return "\n".join(out)


def as_markdown(todos=None):
    todos = list_todos() if todos is None else todos
    icon = {"open": "☐", "in_progress": "◐", "done": "☑", "skipped": "⊘"}
    rows = []
    for t in todos:
        row = f"- {icon[t['status']]} {t['text']}"
        if t["finding"]:
            row += f"\n  - **Finding:** {t['finding']}"
        rows.append(row)
    return "\n".join(rows)
