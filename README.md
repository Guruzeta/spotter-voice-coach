# Spotter — a voice strength coach in your earbuds

Between sets you're out of breath, your hands are on a bar and your phone is in your pocket. Spotter is the
training partner you talk to: it logs every set by voice, works out your next weight from **today's performance
and your training history** (analysis runs in a **Daytona** sandbox), times your rest, and when you're done saves
the workout and **writes next session's plan**.

- **Track:** Open
- **User:** a lifter mid-workout, hands full, who doesn't want to stop and type.
- **Finish line:** the workout is logged and next session's plan is written with prescribed weights.

## What it does
| You say | Spotter does |
|---|---|
| "Squat, two twenty-five for five, felt like an eight" | `log_set` → set appears in today's table |
| "Actually that was six reps" | `edit_set` → fixes it |
| "What's next?" | `next_set` → Daytona computes estimated 1RM (Epley + reps-in-reserve), trend vs history, fatigue drop-off, plateau check → prescribed weight + chart |
| (after a set) | `start_rest` → rest timer on screen |
| "I'm done" | `finish_workout` → Daytona summary (volume, PRs), session saved to `data/sessions/`, history updated, `plans/next-session.md` written |

The agent never does arithmetic itself: every number it says comes from code that ran in the sandbox.

## Architecture
```
Browser (Vite) ── WebRTC ──> ElevenLabs Agent "Spotter" (voice, Claude LLM, patient turn-taking)
   │  client tools: log_set / edit_set / delete_set / next_set / start_rest / finish_workout
   └── fetch ──> FastAPI backend ──> Daytona sandbox "spotter-coach" (pandas/numpy/matplotlib analysis)
```
- `backend/setup_agent.py` creates the agent and its tools via the ElevenLabs API (config as code).
- `agent_prompt.md` is the coach's system prompt (gym-short replies, no mental math).
- `backend/coach.py` holds the analysis that runs in Daytona.
- `data/history.csv` is 8 weeks of seeded training history (`backend/seed_history.py`).

## Run it
```bash
cp .env.example .env    # ELEVENLABS_API_KEY, DAYTONA_API_KEY
cd backend && uv sync && uv run python setup_agent.py && uv run python -m uvicorn app:app --port 8100
cd frontend && npm install && npx vite --port 5180    # open http://localhost:5180
```
