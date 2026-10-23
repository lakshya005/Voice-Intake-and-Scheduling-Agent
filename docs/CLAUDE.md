# CLAUDE.md: Voice Intake & Scheduling Agent

Read `docs/SPEC.md` (what we build) and `docs/LEARNING_PLAN.md` (what I'm learning) before any work.

## Who I am and how to work with me
- I'm a software engineer (Python/Django, React/TypeScript, Postgres, AWS). Voice AI, Pipecat, WebRTC, STT/TTS, and turn detection are all NEW to me.
- This is a portfolio project. I must be able to explain every design decision in an interview. Optimizing for my understanding matters as much as working code.

## Learning mode (always on)
1. **Explain before building.** At the start of each milestone, give me a short explanation of the concepts involved (what it is, why it's needed, the main trade-off) and the plan. Wait for my OK.
2. **I write the core pieces.** For anything marked `[I WRITE]` in SPEC.md, give me a skeleton with TODOs and hints, then review my code. Don't write it for me unless I ask.
3. **Small steps.** One concept per step. Run it, show me the output, then move on.
4. **After each milestone**, quiz me with 3 interview-style questions from LEARNING_PLAN.md and correct my answers.
5. **Decision log.** Append every non-trivial design decision to `docs/DECISIONS.md` (context, options, choice, why). This becomes my interview prep.

## Engineering rules
- Pipecat changes fast (e.g., `PipelineTask` was renamed `PipelineWorker` in 1.3). **Check the current docs (docs.pipecat.ai, docs.pipecat.ai/llms.txt) and the installed version before writing Pipecat code.** Don't rely on memory for its API.
- The database is the source of truth. The LLM never owns booking state. It only calls tools.
- Never commit secrets. Use `.env` + `.env.example`.
- Synthetic data only. No real patient data, ever.
- Don't report or hardcode metrics we haven't measured.
- Never push to `main` without asking me. Work on feature branches, small commits.
- Python: `uv`, type hints, `ruff`. Frontend: Vite + React + TypeScript, strict mode.
