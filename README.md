# Talk to Your Experiment

A voice research partner for people drowning in LLM-generated experiment code, logs and plots.
You ask out loud what your experiment actually shows. The agent **runs the real analysis in a Daytona sandbox**,
**sketches the explanation step by step on a whiteboard** while it talks, and **saves a report** (plus an
optional recorded explainer video) to your repo.

- **Track:** Open (voice → code in Daytona)
- **User:** a researcher with a folder of LLM-generated experiment runs they don't have time to read.
- **Finish line:** a verified finding, explained at their level, saved as a report with figures in the repo.

## How it works

```
Browser (Vite)                          ElevenLabs Agent (voice, LLM, turn-taking)
  ├─ @elevenlabs/client  <── WebRTC ──>   calls client tools:
  ├─ Mermaid hand-drawn whiteboard          get_experiment_overview → /api/experiment
  ├─ tab recorder → explainer .webm         run_analysis            → /api/run → Daytona sandbox
  └─ client tools ── fetch ──> FastAPI      sketch                  → whiteboard (in browser)
                                            save_report             → /api/report → reports/
```

- `backend/sandbox.py` keeps one warm Daytona sandbox with the experiment folder uploaded; agent-written
  pandas/matplotlib code runs there and figures come back as PNGs.
- `backend/setup_agent.py` creates the agent and its tools via the ElevenLabs API (config as code).
- `agent/prompt.md` is the agent's system prompt.
- `demo_experiment/` is a fake learning-rate sweep with real "stories" in it (a warmup-free run that spikes, a run that diverges).

## Run it

```bash
cp .env.example .env            # add ELEVENLABS_API_KEY and DAYTONA_API_KEY
cd backend && uv sync && uv run python setup_agent.py   # creates the agent, writes its id to .env
uv run uvicorn app:app --port 8000 --reload
cd ../frontend && npm install && npm run dev            # open http://localhost:5173
```

Re-run `setup_agent.py` after editing `agent/prompt.md` or tool definitions to update the agent in place.
