"""The thin agent loop (0.12.x / 0.20.0).

Turns the config-only Research crew into an operator: a bounded plan → observe → replan loop
(``agent/llm.py`` + ``agent/planner.py``) turns a thread + its open claims + the instrument
catalog — and, on a replan, server-derived observations — into a validated plan of *existing*
instrument runs, which the orchestrator (``services/agent_runs.py``) executes through the same
``run_instrument`` chokepoint humans use. This package holds the LLM-facing pieces (the client,
the pure planner, and observation rendering); the ledger mechanics stay in ``services/``.
"""
