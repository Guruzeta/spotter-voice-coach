"""Who Sam is talking to. Global across projects, so explanations are tuned to the person everywhere.

profile/settings.json       explicit controls: level + preferred explanation styles
profile/PROFILE.md          what Sam has learned about the person (written by calibration, appended by notes)
profile/writing_samples.md  things the person wrote, used to match their vocabulary and depth
"""
import json
import threading
from datetime import datetime
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profile"
SETTINGS = PROFILE_DIR / "settings.json"
PROFILE = PROFILE_DIR / "PROFILE.md"
SAMPLES = PROFILE_DIR / "writing_samples.md"

LEVELS = {
    "auto": "Infer from the profile and adapt as you go.",
    "intro": "Curious newcomer: no jargon, everyday analogies, one idea at a time.",
    "undergrad": "Undergrad in a quantitative field: basic calculus, linear algebra, probability; define field-specific terms.",
    "grad": "Grad student / practitioner: comfortable with equations and standard methods; skip basics, focus on why.",
    "expert": "Expert peer: terse, precise, technical; go straight to subtleties, caveats and assumptions.",
}
STYLES = {
    "intuition": "Lead with the physical/geometric intuition before any formula.",
    "math": "Show the governing equations and derive the key step; write them on the board.",
    "code": "Point to the exact lines of code that implement each idea.",
    "analogies": "Use concrete analogies from everyday life or other fields.",
    "visual": "Draw it: diagrams and plots first, words second.",
}
DEFAULT = {"level": "auto", "styles": ["intuition", "visual"]}
_lock = threading.Lock()


def _init():
    PROFILE_DIR.mkdir(exist_ok=True)
    if not SETTINGS.exists():
        SETTINGS.write_text(json.dumps(DEFAULT, indent=2))
    if not PROFILE.exists():
        PROFILE.write_text("# About the researcher\n\n(Not calibrated yet.)\n")


def get() -> dict:
    with _lock:
        _init()
        settings = {**DEFAULT, **json.loads(SETTINGS.read_text())}
        samples = SAMPLES.read_text() if SAMPLES.exists() else ""
        return {
            "settings": settings,
            "profile": PROFILE.read_text(),
            "samples_chars": len(samples),
            "levels": list(LEVELS),
            "styles": list(STYLES),
        }


def set_settings(level: str | None = None, styles: list[str] | None = None) -> dict:
    with _lock:
        _init()
        s = {**DEFAULT, **json.loads(SETTINGS.read_text())}
        if level:
            if level not in LEVELS:
                raise ValueError(f"level must be one of {list(LEVELS)}")
            s["level"] = level
        if styles is not None:
            bad = [x for x in styles if x not in STYLES]
            if bad:
                raise ValueError(f"unknown styles {bad}; choose from {list(STYLES)}")
            s["styles"] = styles
        SETTINGS.write_text(json.dumps(s, indent=2))
    return get()


def replace_profile(markdown: str) -> dict:
    with _lock:
        _init()
        PROFILE.write_text(markdown.strip() + f"\n\n_Last calibrated {datetime.now():%Y-%m-%d %H:%M}_\n")
    return get()


def add_note(note: str) -> dict:
    with _lock:
        _init()
        text = PROFILE.read_text()
        if "## Notes" not in text:
            text = text.rstrip() + "\n\n## Notes\n"
        PROFILE.write_text(text.rstrip() + f"\n- {note.strip()}\n")
    return get()


def add_sample(text: str) -> dict:
    with _lock:
        _init()
        with SAMPLES.open("a") as f:
            f.write(f"\n\n--- sample added {datetime.now():%Y-%m-%d %H:%M} ---\n{text.strip()[:8000]}\n")
    return get()


def context(include_samples: bool = False) -> str:
    """Text block for the agent describing who it is talking to and how to explain."""
    p = get()
    s = p["settings"]
    lines = [
        f"LEVEL: {s['level']} — {LEVELS[s['level']]}",
        "STYLES: " + "; ".join(f"{x} ({STYLES[x]})" for x in s["styles"]) if s["styles"] else "STYLES: none selected",
        "",
        p["profile"].strip(),
    ]
    if SAMPLES.exists():
        samples = SAMPLES.read_text()
        budget = 6000 if include_samples else 1500
        lines += ["", f"WRITING SAMPLES BY THE RESEARCHER (match their vocabulary and depth; {len(samples)} chars total, showing up to {budget}):", samples[-budget:]]
    return "\n".join(lines)
