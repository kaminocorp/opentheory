"""Toolbench test fixtures."""

import pytest

from app.toolbench.execution.policy import reset_run_slot_semaphore


@pytest.fixture(autouse=True)
def _reset_execution_semaphore():
    reset_run_slot_semaphore()
    yield
    reset_run_slot_semaphore()