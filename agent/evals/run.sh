#!/bin/sh
# One command: free the slots, run the scripted suite, then check the bot's promises against the database.
# Run from agent/:  sh evals/run.sh
set -e
uv run python evals/reset.py
FIRST=$(docker compose -f ../docker-compose.yml exec -T postgres psql -U voice -d voice_intake -tAc "SELECT coalesce(max(id),0)+1 FROM calls")
SUITE=0
uv run python -m pipecat.evals suite evals/manifest.yaml || SUITE=$?
uv run python -m evals.ledger --since-id "$FIRST" || SUITE=$?
exit $SUITE
