"""
ADR-001: Explicit Task Identity, Finite Execution & Unified Run Contract.

Unified request and result envelope for all agent entrypoints:
- CLI (REPL / single-query)
- WebSocket (Gateway Dashboard)
- A2A (Agent-to-Agent protocol)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class RunStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    EXHAUSTED = "exhausted"
    CANCELLED = "cancelled"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass
class RunLimits:
    max_iterations: Optional[int] = None
    max_turns: Optional[int] = None
    budget_tokens: Optional[int] = None
    timeout_seconds: Optional[float] = None


@dataclass
class RunRequest:
    input: str
    run_id: str = ""
    session_id: Optional[str] = None
    limits: Optional[RunLimits] = None
    on_step: Optional[Callable] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    status: RunStatus
    output: str
    error: Optional[str] = None
    usage: dict[str, int] = field(default_factory=dict)
    run_id: str = ""
    session_id: str = ""
    iterations: int = 0
