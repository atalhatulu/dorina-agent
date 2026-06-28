"""Workflow Runner — updated runner using WorkflowEngine for DAG execution.

Backward-compatible with the original simple step-runner interface.
Now delegates to WorkflowEngine internally for full DAG support.
"""

from __future__ import annotations
import asyncio
import json
from typing import Any

from core.logger import log
from core.constants import t
from workflows.graph import WorkflowGraph
from workflows.engine import WorkflowEngine, WorkflowState


class WorkflowRunner:
    """Workflow runner — simple step interface + full DAG execution.

    Compatible with the original step-based interface. Internally
    uses WorkflowEngine for graph-based execution when using DAGs.
    """

    def __init__(self):
        self.steps: list[dict] = []
        self.engine = WorkflowEngine()

    def define_steps(self, steps: list[dict]):
        """Define sequential steps (backward-compatible)."""
        self.steps = steps
        log.info(f"Workflow: {len(steps)} steps defined")

    def execute(self, input_data: str) -> str:
        """Execute steps sequentially (backward-compatible).

        Each step can be:
        - {'action': 'terminal', 'command': '...'}: run shell command
        - {'action': 'template', 'template': '...'}: string template with {data}
        - {'action': callable}: python function
        - {'action': 'llm', 'prompt': '...', 'system_prompt': '...'}: LLM call
        - {'action': 'tool', 'tool': '...', 'params': {...}}: tool execution
        """
        import subprocess

        data = input_data
        results = []
        for i, step in enumerate(self.steps):
            name = step.get("name", f"step_{i}")
            log.info(f"  Step [{i+1}/{len(self.steps)}]: {name}")

            action = step.get("action")
            if action is None:
                data = f"[{name}: {data}]"
            elif callable(action):
                data = action(data)
            elif isinstance(action, str):
                if action == "terminal":
                    cmd = step.get("command", "")
                    try:
                        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                        data = r.stdout or r.stderr or "done"
                    except Exception as e:
                        data = f"error: {e}"
                elif action == "llm":
                    from orchestrator.reasoning import ReasoningEngine
                    prompt = step.get("prompt", "{data}").replace("{data}", str(data))
                    system = step.get("system_prompt", "You are a helpful assistant.")
                    engine = ReasoningEngine()
                    result = engine.think(
                        system_prompt=system,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    data = result.get("content", "")
                elif action == "tool":
                    tool_name = step.get("tool", "")
                    params = step.get("params", {})
                    params_str = {k: str(v).replace("{data}", str(data)) if isinstance(v, str) else v
                                  for k, v in params.items()}
                    from tools.registry import registry
                    tool_def = registry.get(tool_name)
                    if tool_def:
                        handler = tool_def.handler
                        if tool_def.is_async:
                            loop = asyncio.new_event_loop()
                            try:
                                result = loop.run_until_complete(handler(**params_str))
                            finally:
                                loop.close()
                        else:
                            result = handler(**params_str)
                        data = str(result)[:5000]
                    else:
                        data = f"error: tool '{tool_name}' not found"
                else:
                    data = action.replace("{data}", str(data))

            log.info(f"    -> {str(data)[:80]}")
            results.append({"step": name, "result": str(data)[:200]})

        return json.dumps({"success": True, "steps": len(self.steps), "final": str(data)[:500]})

    # ── DAG-based execution ─────────────────────────────────────

    def execute_dag(self, graph: WorkflowGraph, input_data: Any = "") -> WorkflowState:
        """Execute a DAG-based workflow asynchronously."""
        loop = asyncio.new_event_loop()
        try:
            state = loop.run_until_complete(self.engine.run(graph, input_data))
            return state
        finally:
            loop.close()

    def execute_from_yaml(self, yaml_path: str, input_data: Any = "") -> str:
        """Load workflow definition from YAML and execute.

        YAML format:
        ```yaml
        nodes:
          - id: input
            type: Input
          - id: llm1
            type: LLM
            config:
              prompt: "Analyze: {input}"
          - id: output
            type: Output
        edges:
          - source: input
            target: llm1
          - source: llm1
            target: output
        ```
        """
        import yaml
        from pathlib import Path

        path = Path(yaml_path)
        if not path.exists():
            return json.dumps({"success": False, "error": f"File not found: {yaml_path}"})

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        graph = WorkflowGraph()
        for node_data in data.get("nodes", []):
            graph.add_node(
                node_id=node_data["id"],
                node_type=node_data.get("type", "LLM"),
                config=node_data.get("config", {}),
            )
        for edge_data in data.get("edges", []):
            graph.add_edge(
                source=edge_data["source"],
                target=edge_data["target"],
                condition=edge_data.get("condition"),
            )

        state = self.execute_dag(graph, input_data)
        return json.dumps(state.to_dict(), indent=2, ensure_ascii=False)

    def get_checkpoints(self) -> list[dict]:
        """List all workflow checkpoints."""
        return self.engine.get_checkpoints()

    def resume_workflow(self, execution_id: str) -> str:
        """Resume a paused workflow from checkpoint."""
        loop = asyncio.new_event_loop()
        try:
            state = loop.run_until_complete(self.engine.resume(execution_id))
            if state is None:
                return json.dumps({"success": False, "error": f"Checkpoint {execution_id} not found"})
            return json.dumps(state.to_dict(), indent=2, ensure_ascii=False)
        finally:
            loop.close()


workflows = WorkflowRunner()
