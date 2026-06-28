"""Workflow Engine — DAG-based workflow execution with checkpoint support.

Executes a WorkflowGraph by traversing nodes in topological order,
handling conditions and loops, and supporting save/restore checkpoints.

Inspired by CrewAI Flow and LangGraph's checkpoint system.
"""

from __future__ import annotations
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from core.logger import log
from core.constants import t, PROJECT_ROOT
from workflows.graph import WorkflowGraph
from workflows.nodes import (
    BaseNode, NodeResult,
    InputNode, OutputNode, LLMNode, ToolNode, CodeNode,
    ConditionNode, LoopNode, TerminalNode, SleepNode,
)

# Registry mapping node type strings -> node classes
NODE_TYPE_REGISTRY: dict[str, type[BaseNode]] = {
    "Input": InputNode,
    "Output": OutputNode,
    "LLM": LLMNode,
    "Tool": ToolNode,
    "Code": CodeNode,
    "Condition": ConditionNode,
    "Loop": LoopNode,
    "Terminal": TerminalNode,
    "Sleep": SleepNode,
}


class WorkflowState:
    """Serializable workflow execution state for checkpointing."""

    def __init__(self):
        self.execution_id: str = ""
        self.graph_data: dict | None = None
        self.completed_nodes: dict[str, dict] = {}  # node_id -> NodeResult.to_dict()
        self.current_node: str | None = None
        self.pending_nodes: list[str] = []
        self.context: dict[str, Any] = {}
        self.status: str = "pending"  # pending, running, paused, completed, error
        self.error: str | None = None
        self.started_at: float = 0.0
        self.updated_at: float = 0.0
        self.metadata: dict = {}

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "graph": self.graph_data,
            "completed_nodes": self.completed_nodes,
            "current_node": self.current_node,
            "pending_nodes": self.pending_nodes,
            "context": {k: str(v)[:500] for k, v in self.context.items()},
            "status": self.status,
            "error": self.error,
            "started_at": self.started_at,
            "updated_at": time.time(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowState:
        state = cls()
        state.execution_id = data.get("execution_id", "")
        state.graph_data = data.get("graph")
        state.completed_nodes = data.get("completed_nodes", {})
        state.current_node = data.get("current_node")
        state.pending_nodes = data.get("pending_nodes", [])
        state.context = data.get("context", {})
        state.status = data.get("status", "pending")
        state.error = data.get("error")
        state.started_at = data.get("started_at", 0.0)
        state.updated_at = data.get("updated_at", 0.0)
        state.metadata = data.get("metadata", {})
        return state


class WorkflowEngine:
    """DAG-based workflow execution engine with checkpoint support.

    Usage:
        graph = WorkflowGraph()
        graph.add_node("input", "Input", {"description": "User query"})
        graph.add_node("llm", "LLM", {"prompt": "Analyze: {input}", "system_prompt": "..."})
        graph.add_node("output", "Output", {})
        graph.add_edge("input", "llm")
        graph.add_edge("llm", "output")

        engine = WorkflowEngine()
        result = await engine.run(graph, input_data="Hello world")
    """

    def __init__(self, checkpoint_dir: str | Path | None = None):
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else (PROJECT_ROOT / "data" / "workflow_checkpoints")
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        graph: WorkflowGraph,
        input_data: Any = "",
        execution_id: str | None = None,
        metadata: dict | None = None,
    ) -> WorkflowState:
        """Execute a workflow graph from start to finish.

        Args:
            graph: The WorkflowGraph to execute
            input_data: Initial input data
            execution_id: Optional execution ID (for resuming)
            metadata: Optional metadata for checkpointing

        Returns:
            WorkflowState with all results
        """
        state = WorkflowState()
        state.execution_id = execution_id or str(uuid.uuid4())
        state.graph_data = graph.to_dict()
        state.started_at = time.time()
        state.status = "running"
        state.metadata = metadata or {}
        state.context["_input"] = input_data

        # Validate graph
        errors = graph.validate()
        if errors:
            state.status = "error"
            state.error = f"Graph validation failed: {'; '.join(errors)}"
            return state

        # Get execution order
        try:
            execution_order = graph.topological_sort()
        except ValueError as e:
            state.status = "error"
            state.error = str(e)
            return state

        state.pending_nodes = list(execution_order)
        log.info(f"[Workflow:{state.execution_id}] Başlatıldı: {len(execution_order)} node")

        # Execute graph
        loop_detector: dict[str, int] = {}  # Track loop iterations per node
        completed_something = True

        while state.pending_nodes and completed_something:
            completed_something = False
            next_batch = []

            # Find all nodes whose dependencies are met
            for node_id in list(state.pending_nodes):
                if node_id in state.completed_nodes:
                    state.pending_nodes.remove(node_id)
                    continue

                parents = graph.get_parents(node_id)
                all_parents_done = all(p in state.completed_nodes for p in parents)

                if not all_parents_done:
                    continue

                # Check conditions for this node
                condition_met = True
                for edge in graph.edges:
                    if edge.target == node_id and edge.condition is not None:
                        parent_result = state.completed_nodes.get(edge.source, {})
                        parent_data = parent_result.get("data", "")
                        # If condition is set, only proceed if parent result matches
                        if str(parent_data).lower() != edge.condition.lower():
                            condition_met = False
                            break

                if condition_met:
                    next_batch.append(node_id)
                    completed_something = True

            if not next_batch:
                break  # No more nodes can run

            # Execute ready nodes (can run parallel if independent)
            for node_id in next_batch:
                state.pending_nodes.remove(node_id)
                state.current_node = node_id

                # Build context for this node
                node_context = dict(state.context)
                node_context["_parent_results"] = {
                    p: NodeResult.from_dict(state.completed_nodes[p])
                    for p in graph.get_parents(node_id)
                    if p in state.completed_nodes
                }
                last_result = None
                for p in graph.get_parents(node_id):
                    if p in state.completed_nodes:
                        last_result = NodeResult.from_dict(state.completed_nodes[p])
                if last_result:
                    node_context["_last_result"] = {"data": last_result.data}

                # Create node instance and execute
                node_def = graph.nodes[node_id]
                node_instance = self._create_node(node_def)
                if not node_instance:
                    state.completed_nodes[node_id] = NodeResult(
                        data="", node_id=node_id,
                        status="error",
                        error=f"Unknown node type: {node_def.type}",
                    ).to_dict()
                    continue

                try:
                    result = await node_instance.execute(node_context)
                    state.completed_nodes[node_id] = result.to_dict()

                    log.info(f"[Workflow] Node {node_id} ({node_def.type}): {result.status}")

                    if result.status == "error":
                        log.warning(f"[Workflow] Node {node_id} hatası: {result.error}")

                except Exception as e:
                    state.completed_nodes[node_id] = NodeResult(
                        data="", node_id=node_id, status="error", error=str(e),
                    ).to_dict()

                # Handle loop nodes
                if node_def.type == "Loop":
                    loop_data = state.completed_nodes.get(node_id, {}).get("data", "")
                    if loop_data and "loop_iteration" in loop_data:
                        loop_counter = loop_detector.get(node_id, 0) + 1
                        loop_detector[node_id] = loop_counter
                        # Re-add loop body nodes to pending
                        loop_body = node_def.config.get("loop_nodes", [])
                        for body_node in loop_body:
                            if body_node in state.pending_nodes:
                                continue
                            if body_node in state.completed_nodes:
                                del state.completed_nodes[body_node]
                            state.pending_nodes.append(body_node)

                # Save checkpoint after each node
                self._save_checkpoint(state)

            # After each batch, check if we should continue to loop body execution
            # by re-adding any nodes that became re-enabled

        # Check if all nodes were completed
        all_nodes = set(graph.nodes.keys())
        completed = set(state.completed_nodes.keys())
        failed = all_nodes - completed

        state.current_node = None
        if failed:
            state.status = "error"
            state.error = f"Nodes not reached: {', '.join(failed)}"
        else:
            state.status = "completed"

        state.updated_at = time.time()
        self._save_checkpoint(state)

        elapsed = time.time() - state.started_at
        log.info(f"[Workflow:{state.execution_id}] {state.status} ({elapsed:.1f}s)")

        return state

    async def run_sync(self, graph: WorkflowGraph, input_data: Any = "") -> WorkflowState:
        """Synchronous wrapper for run()."""
        return await self.run(graph, input_data)

    def _create_node(self, node_def) -> BaseNode | None:
        """Create a node instance from its definition."""
        node_class = NODE_TYPE_REGISTRY.get(node_def.type)
        if not node_class:
            return None
        return node_class(node_id=node_def.id, config=node_def.config)

    # ── Checkpoint System ────────────────────────────────────────

    def _save_checkpoint(self, state: WorkflowState) -> str | None:
        """Save execution state to disk as checkpoint."""
        try:
            checkpoint_path = self.checkpoint_dir / f"{state.execution_id}.json"
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
            return str(checkpoint_path)
        except Exception as e:
            log.warning(f"Checkpoint save failed: {e}")
            return None

    def load_checkpoint(self, execution_id: str) -> WorkflowState | None:
        """Load execution state from checkpoint."""
        checkpoint_path = self.checkpoint_dir / f"{execution_id}.json"
        if not checkpoint_path.exists():
            return None
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                data = json.load(f)
            return WorkflowState.from_dict(data)
        except Exception as e:
            log.warning(f"Checkpoint load failed: {e}")
            return None

    async def resume(self, execution_id: str) -> WorkflowState | None:
        """Resume a paused workflow from checkpoint."""
        state = self.load_checkpoint(execution_id)
        if not state:
            return None

        if state.status != "paused":
            log.warning(f"Workflow {execution_id} status is '{state.status}', cannot resume")
            return state

        # Restore graph from checkpoint
        graph = WorkflowGraph.from_dict(state.graph_data or {})

        state.status = "running"
        # Continue execution from where we left off
        return await self.run(
            graph=graph,
            input_data=state.context.get("_input", ""),
            execution_id=execution_id,
            metadata=state.metadata,
        )

    async def pause(self, execution_id: str) -> bool:
        """Mark a running workflow as paused (next checkpoint will reflect this)."""
        state = self.load_checkpoint(execution_id)
        if not state:
            return False
        state.status = "paused"
        self._save_checkpoint(state)
        return True

    def get_checkpoints(self) -> list[dict]:
        """List all available checkpoints."""
        if not self.checkpoint_dir.exists():
            return []
        checkpoints = []
        for f in sorted(self.checkpoint_dir.glob("*.json"), reverse=True):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                checkpoints.append({
                    "execution_id": data.get("execution_id"),
                    "status": data.get("status"),
                    "completed_nodes": len(data.get("completed_nodes", {})),
                    "started_at": data.get("started_at"),
                    "updated_at": data.get("updated_at"),
                    "file": str(f),
                })
            except Exception:
                pass
        return checkpoints[:20]

    def delete_checkpoint(self, execution_id: str) -> bool:
        """Delete a checkpoint."""
        checkpoint_path = self.checkpoint_dir / f"{execution_id}.json"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            return True
        return False


# ── Default instance ─────────────────────────────────────────────

workflow_engine = WorkflowEngine()
