"""A project's open questions, stored as a markdown checklist (projects/<slug>/TODO.md).

    - [ ] open        - [~] in progress        - [x] done        - [-] skipped
    Done items carry their verified finding:  - [x] question — Finding: ...
"""
import re
import threading

from projects import Project

MARKS = {" ": "open", "~": "in_progress", "x": "done", "-": "skipped"}
SYMBOL = {v: k for k, v in MARKS.items()}
LINE = re.compile(r"^- \[([ ~x\-])\] (.*?)(?: — Finding: (.*))?$")
_lock = threading.Lock()


def _read(p: Project):
    header, items = [], []
    for line in p.todo_path.read_text().splitlines() if p.todo_path.exists() else []:
        m = LINE.match(line.strip())
        if m:
            items.append({"status": MARKS[m.group(1)], "text": m.group(2).strip(), "finding": (m.group(3) or "").strip()})
        elif not items:
            header.append(line)
    return header or ["# Open questions"], items


def _write(p: Project, header, items):
    lines = [*header]
    if lines and lines[-1].strip():
        lines.append("")
    for it in items:
        line = f"- [{SYMBOL[it['status']]}] {it['text']}"
        if it["finding"]:
            line += f" — Finding: {it['finding']}"
        lines.append(line)
    p.todo_path.write_text("\n".join(lines) + "\n")


def list_todos(p: Project):
    with _lock:
        _, items = _read(p)
    return [{"id": i + 1, **it} for i, it in enumerate(items)]


def update_todo(p: Project, todo_id: int, status: str, finding: str = ""):
    if status not in SYMBOL:
        raise ValueError(f"status must be one of {list(SYMBOL)}")
    with _lock:
        header, items = _read(p)
        if not 1 <= todo_id <= len(items):
            raise ValueError(f"no to-do with id {todo_id}; ids are 1..{len(items)}")
        if status == "in_progress":  # only one thing in progress at a time
            for it in items:
                if it["status"] == "in_progress":
                    it["status"] = "open"
        items[todo_id - 1]["status"] = status
        if finding:
            items[todo_id - 1]["finding"] = finding.replace("\n", " ").strip()
        _write(p, header, items)
    return list_todos(p)


def add_todo(p: Project, text: str):
    with _lock:
        header, items = _read(p)
        items.append({"status": "open", "text": text.replace("\n", " ").strip(), "finding": ""})
        _write(p, header, items)
    return list_todos(p)


def reset_todos(p: Project):
    with _lock:
        p.todo_path.write_text(p.todo_seed())
    return list_todos(p)


def as_text(todos):
    if not todos:
        return "(empty)"
    out = []
    for t in todos:
        line = f"{t['id']}. [{t['status']}] {t['text']}"
        if t["finding"]:
            line += f" (finding: {t['finding']})"
        out.append(line)
    return "\n".join(out)


def as_markdown(todos):
    icon = {"open": "☐", "in_progress": "◐", "done": "☑", "skipped": "⊘"}
    rows = []
    for t in todos:
        row = f"- {icon[t['status']]} {t['text']}"
        if t["finding"]:
            row += f"\n  - **Finding:** {t['finding']}"
        rows.append(row)
    return "\n".join(rows) or "(none)"
