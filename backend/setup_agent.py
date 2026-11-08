"""Create (or update) the ElevenLabs agent and its client tools from code.

Usage:  uv run python setup_agent.py
Writes ELEVENLABS_AGENT_ID into the .env it loaded keys from.
"""
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv

ENV_PATH = find_dotenv(usecwd=True)
load_dotenv(ENV_PATH)

API = "https://api.elevenlabs.io/v1"
KEY = os.getenv("ELEVENLABS_API_KEY")
REPO = Path(__file__).resolve().parent.parent
IDS_FILE = REPO / "agent" / "tool_ids.json"

TOOLS = [
    {
        "type": "client",
        "name": "get_experiment_overview",
        "description": "Returns the experiment's notes, run configs, metric column names and training code. Call once, silently, at the start.",
        "expects_response": True,
        "response_timeout_secs": 15,
        "pre_tool_speech": "off",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "client",
        "name": "run_analysis",
        "description": "Run Python analysis code in a Daytona cloud sandbox whose working directory is the experiment folder. Returns printed output and any figure URLs.",
        "expects_response": True,
        "response_timeout_secs": 90,
        "pre_tool_speech": "force",
        "parameters": {
            "type": "object",
            "properties": {
                "purpose": {"type": "string", "description": "One short sentence: what this analysis checks."},
                "code": {"type": "string", "description": "Python code. pd, np, plt are pre-imported. Print only key numbers. At most one plt figure; do not savefig."},
            },
            "required": ["purpose", "code"],
        },
    },
    {
        "type": "client",
        "name": "sketch",
        "description": "Draw or update the whiteboard diagram from Mermaid flowchart code. Re-send the whole diagram each time, adding one or two nodes per step.",
        "expects_response": True,
        "response_timeout_secs": 10,
        "pre_tool_speech": "off",
        "parameters": {
            "type": "object",
            "properties": {
                "mermaid": {"type": "string", "description": "Mermaid code starting with 'flowchart LR' or 'flowchart TD'. Quoted, short node labels. Max 8 nodes."},
                "caption": {"type": "string", "description": "A few words describing the current step."},
            },
            "required": ["mermaid"],
        },
    },
    {
        "type": "client",
        "name": "read_file",
        "description": "Read a file from the researcher's repo (in the Daytona sandbox). Notebooks are rendered as text cells with short outputs. Returns numbered lines.",
        "expects_response": True,
        "response_timeout_secs": 30,
        "pre_tool_speech": "auto",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the repo root, as shown in the file tree."},
                "start_line": {"type": "integer", "description": "First line to show (default 1)."},
                "max_lines": {"type": "integer", "description": "How many lines (default 150, max 300)."},
            },
            "required": ["path"],
        },
    },
    {
        "type": "client",
        "name": "search_repo",
        "description": "Case-insensitive text search across the repo (like grep). Use to find where a variable, parameter or concept appears.",
        "expects_response": True,
        "response_timeout_secs": 30,
        "pre_tool_speech": "auto",
        "parameters": {
            "type": "object",
            "properties": {"pattern": {"type": "string", "description": "Text or regex to search for."}},
            "required": ["pattern"],
        },
    },
    {
        "type": "client",
        "name": "remember",
        "description": "Save a durable note to this project's memory so future calls start with it: a verified finding, a decision, a correction from the researcher, or how they like things explained.",
        "expects_response": False,
        "pre_tool_speech": "off",
        "parameters": {
            "type": "object",
            "properties": {"note": {"type": "string", "description": "One self-contained sentence, with numbers where relevant."}},
            "required": ["note"],
        },
    },
    {
        "type": "client",
        "name": "set_explanation_style",
        "description": "Change how you explain, when the researcher asks (e.g. 'more math', 'too basic', 'just intuition'). Updates the controls on their screen and persists.",
        "expects_response": True,
        "response_timeout_secs": 10,
        "pre_tool_speech": "off",
        "parameters": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["auto", "intro", "undergrad", "grad", "expert"], "description": "Explanation level; omit to keep the current one."},
                "styles": {"type": "string", "description": "Comma-separated subset of: intuition, math, code, analogies, visual. Omit to keep current."},
            },
            "required": [],
        },
    },
    {
        "type": "client",
        "name": "update_profile",
        "description": "Rewrite the researcher's profile (used in every future call) after calibrating. Markdown with sections: Background, Strong in, Shaky on, How to explain to them, Vocabulary they use.",
        "expects_response": True,
        "response_timeout_secs": 15,
        "pre_tool_speech": "off",
        "parameters": {
            "type": "object",
            "properties": {"markdown": {"type": "string", "description": "The complete new profile in markdown, concise (under 250 words)."}},
            "required": ["markdown"],
        },
    },
    {
        "type": "client",
        "name": "note_about_user",
        "description": "Append one lasting observation about the researcher to their profile (e.g. 'Knows directed percolation deeply; skip the basics', 'Prefers seeing the equation before the intuition').",
        "expects_response": False,
        "pre_tool_speech": "off",
        "parameters": {
            "type": "object",
            "properties": {"note": {"type": "string", "description": "One sentence."}},
            "required": ["note"],
        },
    },
    {
        "type": "client",
        "name": "write_on_board",
        "description": "Handwrite one short line on the whiteboard under the diagram: an equation, a key number, or a takeaway. Use unicode math (π, √, ≈, ², →).",
        "expects_response": False,
        "pre_tool_speech": "off",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "At most ~50 characters, e.g. 'T = 2π√(m/k) ≈ 6.28'."}},
            "required": ["text"],
        },
    },
    {
        "type": "client",
        "name": "show_agenda",
        "description": "Write the walkthrough agenda in the corner of the whiteboard and mark which section you're on.",
        "expects_response": False,
        "pre_tool_speech": "off",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {"type": "string", "description": "Section titles separated by ' | ', 2-4 words each, e.g. 'The question | The setup | Energy drift | Stability | Takeaways'."},
                "current": {"type": "integer", "description": "1-based index of the section you're presenting now."},
            },
            "required": ["items", "current"],
        },
    },
    {
        "type": "client",
        "name": "update_todo",
        "description": "Change the status of one item on the researcher's to-do list (shown live on screen and saved to TODO.md). Returns the updated list.",
        "expects_response": True,
        "response_timeout_secs": 10,
        "pre_tool_speech": "off",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "To-do id from the list."},
                "status": {"type": "string", "enum": ["in_progress", "done", "skipped", "open"], "description": "New status."},
                "finding": {"type": "string", "description": "For done: one sentence with the verified answer and key numbers. Otherwise empty."},
            },
            "required": ["id", "status"],
        },
    },
    {
        "type": "client",
        "name": "add_todo",
        "description": "Add a new open question to the researcher's to-do list when they ask to note something for later.",
        "expects_response": True,
        "response_timeout_secs": 10,
        "pre_tool_speech": "off",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The question, phrased briefly."}},
            "required": ["text"],
        },
    },
    {
        "type": "client",
        "name": "save_report",
        "description": "Save a markdown report of the findings (figures from this session are attached automatically) into the researcher's repo.",
        "expects_response": True,
        "response_timeout_secs": 20,
        "pre_tool_speech": "auto",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short report title."},
                "markdown": {"type": "string", "description": "Report body in markdown: headline, what we checked, what we found (real numbers), why, next steps."},
            },
            "required": ["title", "markdown"],
        },
    },
]


def call(client, method, path, body=None):
    r = client.request(method, f"{API}{path}", json=body)
    if r.status_code >= 300:
        print(f"{method} {path} -> {r.status_code}\n{r.text}")
        sys.exit(1)
    return r.json()


def write_env(key, value):
    lines = Path(ENV_PATH).read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    Path(ENV_PATH).write_text("\n".join(lines) + "\n")


def main():
    if not KEY:
        sys.exit(f"ELEVENLABS_API_KEY missing (looked in {ENV_PATH or 'no .env found'})")
    with httpx.Client(headers={"xi-api-key": KEY}, timeout=30) as client:
        old_ids = json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else {}
        tool_ids = {}
        for tool in TOOLS:
            if tool["name"] in old_ids:
                r = client.patch(f"{API}/convai/tools/{old_ids[tool['name']]}", json={"tool_config": tool})
                if r.status_code < 300:
                    tool_ids[tool["name"]] = old_ids[tool["name"]]
                    print(f"updated tool {tool['name']}")
                    continue
            created = call(client, "POST", "/convai/tools", {"tool_config": tool})
            tool_ids[tool["name"]] = created["id"]
            print(f"created tool {tool['name']} -> {created['id']}")
        IDS_FILE.write_text(json.dumps(tool_ids, indent=2) + "\n")

        tts = {"speed": float(os.getenv("AGENT_SPEED") or 0.92)}
        if os.getenv("AGENT_VOICE_ID"):
            tts["voice_id"] = os.getenv("AGENT_VOICE_ID")
        body = {
            "name": "Talk to your experiment",
            "conversation_config": {
                "agent": {
                    "first_message": "Hey, it's Sam. I've got your project open. Ready when you are.",
                    "language": "en",
                    "prompt": {
                        "prompt": (REPO / "agent" / "prompt.md").read_text(),
                        "llm": os.getenv("AGENT_LLM") or "claude-haiku-4-5",
                        "temperature": 0.3,
                        "tool_ids": list(tool_ids.values()),
                    },
                },
                "tts": tts,
                # "patient" waits longer before deciding the user finished talking;
                # turn_timeout is how long Sam stays silent before nudging.
                "turn": {"turn_eagerness": "patient", "turn_timeout": 12},
                "conversation": {
                    "max_duration_seconds": 1200,
                    "client_events": ["audio", "interruption", "agent_response", "user_transcript", "client_tool_call"],
                },
            },
            "platform_settings": {"auth": {"enable_auth": True}},
        }
        agent_id = os.getenv("ELEVENLABS_AGENT_ID")
        if agent_id:
            call(client, "PATCH", f"/convai/agents/{agent_id}", body)
            print(f"updated agent {agent_id}")
        else:
            agent_id = call(client, "POST", "/convai/agents/create", body)["agent_id"]
            write_env("ELEVENLABS_AGENT_ID", agent_id)
            print(f"created agent {agent_id} (saved to {ENV_PATH})")


if __name__ == "__main__":
    main()
