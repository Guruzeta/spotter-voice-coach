"""Create (or update) the Spotter ElevenLabs agent and its client tools from code.

Usage:  uv run python setup_agent.py      (writes ELEVENLABS_AGENT_ID into .env)
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
IDS_FILE = REPO / "tool_ids.json"

SET_PARAMS = {
    "exercise": {"type": "string", "description": "e.g. squat, bench press, deadlift, goblet squat"},
    "weight_lb": {"type": "number", "description": "Weight in pounds."},
    "reps": {"type": "integer", "description": "Reps completed."},
    "rpe": {"type": "number", "description": "Effort out of 10 (RPE). 8 = two reps left in the tank."},
}


def tool(name, description, properties=None, required=(), expects=True, timeout=10, pre="off"):
    return {
        "type": "client",
        "name": name,
        "description": description,
        "expects_response": expects,
        "response_timeout_secs": timeout,
        "pre_tool_speech": pre,
        "parameters": {"type": "object", "properties": properties or {}, "required": list(required)},
    }


TOOLS = [
    tool("log_set", "Log a completed set. Returns the set number and today's list.", SET_PARAMS, ["exercise", "weight_lb", "reps"]),
    tool(
        "edit_set",
        "Correct a logged set by its number (only pass fields that change).",
        {"set_number": {"type": "integer", "description": "Set number from the list."}, **SET_PARAMS},
        ["set_number"],
    ),
    tool("delete_set", "Remove a logged set by its number.", {"set_number": {"type": "integer", "description": "Set number."}}, ["set_number"]),
    tool(
        "next_set",
        "Run the training analysis in a Daytona sandbox: today's estimated max vs history, trend, fatigue, and the prescribed weight for the next set.",
        {
            "exercise": {"type": "string", "description": "Lift to prescribe."},
            "reps": {"type": "integer", "description": "Target reps (default 5)."},
            "rpe": {"type": "number", "description": "Target RPE (default 8)."},
        },
        ["exercise"],
        timeout=45,
        pre="force",
    ),
    tool(
        "start_rest",
        "Start a visible rest timer on the lifter's screen.",
        {"seconds": {"type": "integer", "description": "Rest length in seconds."}},
        ["seconds"],
        expects=False,
    ),
    tool("finish_workout", "End the workout: save it, update history, compute PRs and write next session's plan (runs in Daytona).", timeout=60, pre="force"),
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
        sys.exit("ELEVENLABS_API_KEY missing")
    with httpx.Client(headers={"xi-api-key": KEY}, timeout=30) as client:
        old = json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else {}
        ids = {}
        for t in TOOLS:
            if t["name"] in old and client.patch(f"{API}/convai/tools/{old[t['name']]}", json={"tool_config": t}).status_code < 300:
                ids[t["name"]] = old[t["name"]]
                continue
            ids[t["name"]] = call(client, "POST", "/convai/tools", {"tool_config": t})["id"]
            print(f"created tool {t['name']}")
        IDS_FILE.write_text(json.dumps(ids, indent=2) + "\n")

        tts = {"speed": 1.0}
        if os.getenv("AGENT_VOICE_ID"):
            tts["voice_id"] = os.getenv("AGENT_VOICE_ID")
        body = {
            "name": "Spotter",
            "conversation_config": {
                "agent": {
                    "first_message": "Spotter here. What are we lifting today?",
                    "language": "en",
                    "prompt": {
                        "prompt": (REPO / "agent_prompt.md").read_text(),
                        "llm": os.getenv("AGENT_LLM") or "claude-haiku-4-5",
                        "temperature": 0.3,
                        "tool_ids": list(ids.values()),
                    },
                },
                "tts": tts,
                # Normal eagerness keeps replies fast; long turn_timeout so it does not nag during rest.
                "turn": {"turn_eagerness": "normal", "turn_timeout": 20},
                "conversation": {
                    "max_duration_seconds": 1800,
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
            print(f"created agent {agent_id}")


if __name__ == "__main__":
    main()
