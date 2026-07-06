"""The thin agent loop (0.12.x).

Turns the config-only Research crew into an operator: a bounded planning call (``agent/llm.py`` +
``agent/planner.py``, 0.12.1) turns a thread + its open claims + the instrument catalog into a
validated plan of *existing* instrument runs, which the orchestrator (``services/agent_runs.py``,
0.12.2) executes through the same ``run_instrument`` chokepoint humans use. This package holds the
LLM-facing pieces (the client and the pure planner); the ledger mechanics stay in ``services/``.
"""
