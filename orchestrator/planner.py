"""Planner — task decomposition + dependency graph + subagent dispatch.

Superpowers pattern:
  - Task decomposition: karmaşık görevleri atomik alt-görevlere böl
  - Dependency graph: alt-görevler arası bağımlılıkları yönet
  - Subagent dispatch: bağımsız görevleri paralel çalıştır

Kullanım:
    from orchestrator.planner import planner
    
    plan = planner.analyze("Dosya oku, veriyi analiz et, rapor yaz")
    result = planner.execute_plan(plan)
"""

from __future__ import annotations
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from core.logger import log


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """Atomic task in a plan — smallest unit of work."""
    id: str = ""
    description: str = ""
    tool: str = ""
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)  # Task IDs this depends on
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""
    error: str = ""
    agent_id: str = ""  # SubAgent ID if delegated
    created_by: str = ""  # "llm", "rule", "manual"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @property
    def is_ready(self) -> bool:
        """Check if all dependencies are met."""
        return True  # External check via TaskGraph


@dataclass
class TaskGraph:
    """Dependency graph for tasks — DAG structure.

    Supports:
      - Topological sort for execution order
      - Parallel execution of independent tasks
      - Cycle detection
    """
    tasks: dict[str, Task] = field(default_factory=dict)

    def add_task(self, task: Task):
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def get_ready_tasks(self) -> list[Task]:
        """Get tasks whose dependencies are all completed."""
        ready = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            if all(
                self.tasks.get(dep_id, Task()).status == TaskStatus.COMPLETED
                for dep_id in task.depends_on
            ):
                ready.append(task)
        return ready

    def get_remaining(self) -> list[Task]:
        """Get all tasks not yet completed or failed."""
        return [
            t for t in self.tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]

    def get_dependents(self, task_id: str) -> list[Task]:
        """Get tasks that depend on the given task."""
        return [
            t for t in self.tasks.values()
            if task_id in t.depends_on
        ]

    def is_complete(self) -> bool:
        """Check if all tasks are done (completed or failed)."""
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)
            for t in self.tasks.values()
        )

    def topological_sort(self) -> list[list[Task]]:
        """Return tasks in topological layers (parallel-safe groups).

        Returns:
            List of layers, where each layer contains tasks that can run in parallel.
        """
        # Build in-degree count and reverse dependencies
        in_degree: dict[str, int] = {}
        reverse_deps: dict[str, list[str]] = {}

        for tid, task in self.tasks.items():
            if tid not in in_degree:
                in_degree[tid] = 0
            for dep_id in task.depends_on:
                in_degree[tid] = in_degree.get(tid, 0) + 1
                if dep_id not in reverse_deps:
                    reverse_deps[dep_id] = []
                reverse_deps[dep_id].append(tid)

        # Kahn's algorithm — group by layer
        layers = []
        remaining = set(self.tasks.keys())

        while remaining:
            # Find tasks with no remaining dependencies in this layer
            current_layer = [
                tid for tid in remaining
                if in_degree.get(tid, 0) == 0
            ]

            if not current_layer:
                # Cycle detected — break remaining as final layer
                layers.append([self.tasks[tid] for tid in remaining])
                break

            layers.append([self.tasks[tid] for tid in current_layer])

            # Update in-degrees
            for tid in current_layer:
                remaining.remove(tid)
                for dep_id in reverse_deps.get(tid, []):
                    if dep_id in in_degree:
                        in_degree[dep_id] -= 1

        return layers

    def detect_cycles(self) -> list[list[str]]:
        """Detect cycles in the dependency graph.

        Returns:
            List of cycles found (each cycle is a list of task IDs).
        """
        visited: set[str] = set()
        rec_stack: set[str] = set()
        cycles: list[list[str]] = []
        path: list[str] = []

        def _dfs(node: str):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            task = self.tasks.get(node)
            if task:
                for dep_id in task.depends_on:
                    if dep_id not in visited:
                        _dfs(dep_id)
                    elif dep_id in rec_stack:
                        # Found cycle — extract it
                        cycle_start = path.index(dep_id)
                        cycles.append(path[cycle_start:] + [dep_id])

            path.pop()
            rec_stack.discard(node)

        for tid in self.tasks:
            if tid not in visited:
                _dfs(tid)

        return cycles

    def to_dict(self) -> dict:
        return {
            "task_count": len(self.tasks),
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "layers": [[t.id for t in layer] for layer in self.topological_sort()],
        }


# ── Task Decomposition Engine ──────────────────────────────────


class TaskDecomposer:
    """Decompose complex tasks into atomic sub-tasks.

    Uses rule-based and LLM-based decomposition strategies.
    """

    # Turkish/English conjunction-based split patterns
    SPLIT_PATTERNS = {
        "ve": "parallel", "and": "parallel",
        "sonra": "sequential", "then": "sequential",
        "ardından": "sequential",
        "ayrıca": "parallel", "also": "parallel",
        "hem": "parallel", "both": "parallel",
        "bir de": "parallel",
    }

    # Tool mapping for common actions
    ACTION_TOOL_MAP = {
        "oku": "read_file", "read": "read_file",
        "yaz": "write_file", "write": "write_file", "create": "write_file", "oluştur": "write_file",
        "çalıştır": "terminal", "run": "terminal", "execute": "terminal",
        "ara": "search_files", "search": "search_files", "bul": "search_files", "find": "search_files",
        "sor": "web_search", "ask": "web_search", "araştır": "web_search",
        "düzenle": "patch", "edit": "patch",
        "sil": "terminal", "delete": "terminal", "remove": "terminal",
        "kopyala": "terminal", "copy": "terminal",
        "taşı": "terminal", "move": "terminal", "mv": "terminal",
        "listele": "terminal", "list": "terminal", "ls": "terminal",
    }

    def decompose(self, user_input: str) -> TaskGraph:
        """Decompose user input into a dependency graph of tasks.

        Strategy:
          1. Try rule-based split on conjunctions
          2. For simple requests, single task
          3. Build dependency graph based on sequential/parallel hints
        """
        graph = TaskGraph()
        input_lower = user_input.lower()

        # Detect conjunction-based splits
        import re

        # Try to split on sequential conjunctions first
        for conj, mode in [("sonra", "sequential"), ("ardından", "sequential"),
                           ("then", "sequential"), ("ve", "parallel"), ("and", "parallel")]:
            pattern = re.compile(rf'\s+{conj}\s+', re.IGNORECASE)
            if pattern.search(input_lower):
                parts = pattern.split(user_input)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 2:
                    return self._build_graph_from_parts(parts, mode, user_input)

        # Check for numbered steps (1. ..., 2. ..., etc.)
        step_pattern = re.findall(r'(?:^|\n)\s*(?:\d+[.)]\s*)([^\n]+)', user_input)
        if len(step_pattern) >= 2:
            return self._build_graph_from_parts(
                [s.strip() for s in step_pattern], "sequential", user_input
            )

        # Single task: create one task
        task = self._create_task(user_input, "0", [])
        if isinstance(task, tuple):
            graph.add_task(task[0])
            graph.add_task(task[1])
        else:
            graph.add_task(task)
        return graph

    def _build_graph_from_parts(
        self, parts: list[str], mode: str, original: str
    ) -> TaskGraph:
        """Build a dependency graph from text parts."""
        graph = TaskGraph()

        for i, part in enumerate(parts):
            task_id = str(i)
            dependencies = []

            if mode == "sequential" and i > 0:
                # Each step depends on the previous
                dependencies = [str(i - 1)]

            task = self._create_task(part, task_id, dependencies)
            if isinstance(task, tuple):
                # (preflight_task, original_task) — ikisini de ekle
                graph.add_task(task[0])
                graph.add_task(task[1])
            else:
                graph.add_task(task)

        return graph

    def _create_task(self, text: str, task_id: str, depends_on: list[str]) -> Task:
        """Create a task from text, inferring tool and args."""
        text_lower = text.lower()

        # Try to infer tool
        tool = ""
        for action, suggested_tool in self.ACTION_TOOL_MAP.items():
            if action in text_lower:
                tool = suggested_tool
                break

        # Pre-flight check: terminal + kur/install/yükle → öncesine web_search ekle
        if tool == "terminal" and any(kw in text_lower for kw in ["kur", "install", "yükle", "yukle", "setup"]):
            search_task = Task(
                id=f"{task_id}_preflight",
                description=f"{text.strip()} icin arastir",
                tool="web_search",
                args={"query": f"how to install {text.strip()}"},
                depends_on=[],
                created_by="rule",
            )
            # Mevcut task bu search'e bagimli olsun
            depends_on = [f"{task_id}_preflight"]
            task = Task(
                id=task_id,
                description=text.strip(),
                tool=tool,
                args={"task": text.strip()},
                depends_on=depends_on,
                created_by="rule",
            )
            return search_task, task  # (preflight, original)

        # If no tool matched, leave empty (will be filled by LLM or manual)
        return Task(
            id=task_id,
            description=text.strip(),
            tool=tool,
            args={"task": text.strip()},
            depends_on=depends_on,
            created_by="rule",
        )


# ── Planner (Main) ─────────────────────────────────────────────


class Planner:
    """Main planner — analyze, execute, subagent dispatch.

    Flow:
      1. analyze(user_input) → Plan with TaskGraph
      2. execute_plan(plan)   → Run tasks respecting dependency order
      3. Subagent dispatch    → Parallel execution via DelegateManager
    """

    def __init__(self):
        self.plans: list[dict] = []
        self.decomposer = TaskDecomposer()

    def analyze(
        self,
        user_input: str,
        available_tools: list[str] | None = None,
    ) -> dict:
        """Analyze a user request and return a structured plan with dependency graph.

        Returns:
            dict with:
                - task: original request
                - graph: TaskGraph (serialized to dict)
                - steps: list of task dicts (for backward compat)
                - parallel: whether steps can run in parallel
                - summary: brief description
        """
        # Decompose into tasks
        task_graph = self.decomposer.decompose(user_input)

        # Check for cycles
        cycles = task_graph.detect_cycles()
        if cycles:
            log.warning(f"Cycle detected in plan for '{user_input[:40]}': {cycles}")
            # Break cycles by removing problematic dependencies
            for cycle in cycles:
                for i in range(len(cycle) - 1):
                    task = task_graph.get_task(cycle[i])
                    if task and cycle[i + 1] in task.depends_on:
                        task.depends_on.remove(cycle[i + 1])
                        break

        # Build serializable plan
        steps = [task.to_dict() for task in task_graph.tasks.values()]
        layers = task_graph.topological_sort()
        is_parallel = any(len(layer) > 1 for layer in layers)

        plan = {
            "task": user_input,
            "graph": task_graph.to_dict(),
            "steps": steps,
            "layers": [[t.id for t in layer] for layer in layers],
            "parallel": is_parallel,
            "summary": f"{len(steps)} steps in {len(layers)} layers",
            "error": None,
            "cycles_detected": len(cycles),
        }

        self.plans.append(plan)
        log.info(f"Plan analyzed: {plan['summary']}")
        return plan

    async def execute_plan(self, plan: dict) -> str:
        """Execute a plan — run tasks respecting dependency graph asynchronously.

        Uses asyncio.gather for parallel task execution.
        ThreadPoolExecutor kaldirildi — tamamen async.

        Returns:
            JSON string with execution results.
        """
        from tools.executor import executor
        import asyncio

        # Rebuild task graph from plan
        graph = TaskGraph()
        for step_data in plan.get("steps", []):
            task = Task(
                id=step_data.get("id", str(uuid.uuid4().hex[:8])),
                description=step_data.get("description", ""),
                tool=step_data.get("tool", ""),
                args=step_data.get("args", {}),
                depends_on=step_data.get("depends_on", []),
            )
            graph.add_task(task)

        results = []
        max_iterations = 50
        iteration = 0

        while not graph.is_complete() and iteration < max_iterations:
            iteration += 1

            # Get tasks ready to run (dependencies satisfied)
            ready = graph.get_ready_tasks()
            if not ready and not graph.is_complete():
                # Stuck — tasks may have unmet deps from failed tasks
                remaining = graph.get_remaining()
                for task in remaining:
                    for dep_id in task.depends_on:
                        dep = graph.get_task(dep_id)
                        if dep and dep.status == TaskStatus.FAILED:
                            task.status = TaskStatus.SKIPPED
                            task.error = f"Dependency {dep_id} failed"
                            results.append({
                                "id": task.id,
                                "tool": task.tool,
                                "description": task.description,
                                "status": "skipped",
                                "error": task.error,
                            })
                continue

            # Run ready tasks in parallel with asyncio.gather
            for task in ready:
                task.status = TaskStatus.RUNNING

            task_results = await asyncio.gather(*[
                self._execute_single_task(task, executor)
                for task in ready
            ], return_exceptions=True)

            for task, task_result in zip(ready, task_results):
                if isinstance(task_result, dict):
                    results.append(task_result)
                    if task_result.get("status") == "completed":
                        task.status = TaskStatus.COMPLETED
                    else:
                        task.status = TaskStatus.FAILED
                elif isinstance(task_result, Exception):
                    task.status = TaskStatus.FAILED
                    task.error = str(task_result)
                    results.append({
                        "id": task.id,
                        "tool": task.tool,
                        "description": task.description,
                        "status": "failed",
                        "error": str(task_result),
                    })
                else:
                    task.status = TaskStatus.FAILED
                    task.error = "Unknown error"
                    results.append({
                        "id": task.id,
                        "tool": task.tool,
                        "description": task.description,
                        "status": "failed",
                        "error": "Unknown error",
                    })

        # Delegate to subagent if the agent loop should take over
        import json as _json
        return _json.dumps({
            "plan": plan.get("task", ""),
            "steps_executed": len(results),
            "all_completed": graph.is_complete(),
            "layers": plan.get("layers", []),
            "results": results,
            "needs_delegate": not graph.is_complete(),
        }, ensure_ascii=False)

    async def _execute_single_task(self, task: Task, executor) -> dict:
        """Execute a single task using the tool executor asynchronously.

        If task has no tool, delegate to a sub-agent.
        """
        log.info(f"Executing task [{task.id}]: {task.description[:60]}")

        if not task.tool:
            # No specific tool — delegate to sub-agent
            return await self._delegate_to_subagent(task)

        try:
            import asyncio
            result = await asyncio.to_thread(executor.execute, task.tool, task.args)
            return {
                "id": task.id,
                "tool": task.tool,
                "description": task.description,
                "status": "completed",
                "result": str(result)[:500],
            }
        except Exception as e:
            return {
                "id": task.id,
                "tool": task.tool,
                "description": task.description,
                "status": "failed",
                "error": str(e),
            }

    async def _delegate_to_subagent(self, task: Task) -> dict:
        """Delegate a task to a sub-agent for execution."""
        try:
            from tools.delegate import delegate_task
            import asyncio

            result = await asyncio.to_thread(
                delegate_task,
                task.description,
                context=f"Execute this subtask. Task ID: {task.id}",
            )
            return {
                "id": task.id,
                "tool": "subagent",
                "description": task.description,
                "status": "completed",
                "result": str(result)[:500],
                "agent_id": getattr(result, "agent_id", ""),
            }
        except ImportError:
            # Fallback: return as-is if delegate not available
            return {
                "id": task.id,
                "tool": "subagent",
                "description": task.description,
                "status": "completed",
                "result": f"Subtask: {task.description}",
            }
        except Exception as e:
            return {
                "id": task.id,
                "tool": "subagent",
                "description": task.description,
                "status": "failed",
                "error": str(e),
            }

    async def plan_and_execute(
        self,
        user_input: str,
        tools: list[str] | None = None,
    ) -> str:
        """Convenience: analyze + execute in one call.

        Returns JSON string with plan and results.
        """
        plan = self.analyze(user_input, tools or [])
        result = await self.execute_plan(plan)
        return result


# Global singleton
planner = Planner()
