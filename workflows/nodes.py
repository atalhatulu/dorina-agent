"""Built-in Workflow Node Types — LLM, Tool, Code, Condition, Loop.

Each node type implements execute() and can be serialized for checkpointing.
Inspired by CrewAI Flow and LangGraph node patterns.
"""

from __future__ import annotations
import asyncio
import json
import re
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Any, Callable

from core.logger import log
from core.constants import t


class NodeResult:
    """Result of a node execution with checkpoint support."""
    def __init__(self, data: Any, node_id: str, status: str = "success", error: str | None = None):
        self.data = data
        self.node_id = node_id
        self.status = status  # "success", "error", "skipped"
        self.error = error
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "data": self.data,
            "node_id": self.node_id,
            "status": self.status,
            "error": self.error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NodeResult:
        return cls(
            data=data.get("data"),
            node_id=data.get("node_id", ""),
            status=data.get("status", "success"),
            error=data.get("error"),
        )


class BaseNode(ABC):
    """Abstract base class for all workflow nodes."""

    def __init__(self, node_id: str, config: dict | None = None):
        self.node_id = node_id
        self.config = config or {}

    @abstractmethod
    async def execute(self, context: dict[str, Any]) -> NodeResult:
        ...

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "type": self.__class__.__name__,
            "config": self.config,
        }


class InputNode(BaseNode):
    """Entry point — passes input data into the workflow."""

    async def execute(self, context: dict[str, Any]) -> NodeResult:
        data = context.get("_input", "")
        log.info(f"[Workflow:{self.node_id}] Girdi: {str(data)[:100]}")
        return NodeResult(data=data, node_id=self.node_id)


class OutputNode(BaseNode):
    """Exit point — collects and formats the final output."""

    async def execute(self, context: dict[str, Any]) -> NodeResult:
        parent_results = context.get("_parent_results", {})
        # Collect data from parents
        output_parts = []
        for nid, result in parent_results.items():
            if result and hasattr(result, 'data'):
                output_parts.append(str(result.data))
        output = "\n".join(output_parts)
        log.info(f"[Workflow:{self.node_id}] Çıktı: {str(output)[:100]}")
        return NodeResult(data=output, node_id=self.node_id)


class LLMNode(BaseNode):
    """LLM call node — sends a prompt to the language model.

    Config:
        model: str (optional, uses default if not set)
        prompt: str (template with {input} variable)
        system_prompt: str (optional)
        temperature: float (0.0-1.0)
        max_tokens: int
    """

    async def execute(self, context: dict[str, Any]) -> NodeResult:
        prompt_template = self.config.get("prompt", "{input}")
        system_prompt = self.config.get("system_prompt", "You are a helpful assistant.")
        temperature = self.config.get("temperature", 0.7)
        max_tokens = self.config.get("max_tokens", 4096)

        input_data = context.get("_last_result", {}).get("data", "")
        prompt = prompt_template.replace("{input}", str(input_data))
        # Also replace {context} with full context dump
        context_str = json.dumps({k: str(v)[:200] for k, v in context.items() if k.startswith("_")}, indent=2)
        prompt = prompt.replace("{context}", context_str)

        log.info(f"[Workflow:{self.node_id}] LLM çağrısı...")

        try:
            from orchestrator.reasoning import ReasoningEngine
            engine = ReasoningEngine()
            result = engine.think(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            content = result.get("content", "")
            return NodeResult(
                data=content,
                node_id=self.node_id,
            )
        except Exception as e:
            return NodeResult(
                data="",
                node_id=self.node_id,
                status="error",
                error=str(e),
            )


class ToolNode(BaseNode):
    """Tool execution node — runs a registered tool.

    Config:
        tool: str (tool name, e.g. "web_search", "read_file")
        params: dict (parameters to pass to the tool, supports {input} template)
        timeout: int (seconds)
    """

    async def execute(self, context: dict[str, Any]) -> NodeResult:
        tool_name = self.config.get("tool", "")
        params = dict(self.config.get("params", {}))
        timeout = self.config.get("timeout", 30)

        # Template substitution in params
        input_data = context.get("_last_result", {}).get("data", "")
        for key, value in params.items():
            if isinstance(value, str) and "{input}" in value:
                params[key] = value.replace("{input}", str(input_data))

        log.info(f"[Workflow:{self.node_id}] Araç: {tool_name}({params})")

        try:
            from tools.registry import registry
            tool_def = registry.get(tool_name)
            if not tool_def:
                return NodeResult(
                    data="",
                    node_id=self.node_id,
                    status="error",
                    error=f"Tool '{tool_name}' not found",
                )

            handler = tool_def.handler
            if tool_def.is_async:
                result = await handler(**params)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: handler(**params)
                )

            return NodeResult(
                data=str(result)[:10000],
                node_id=self.node_id,
            )
        except Exception as e:
            return NodeResult(
                data="",
                node_id=self.node_id,
                status="error",
                error=str(e),
            )


class CodeNode(BaseNode):
    """Code execution node — runs inline Python code.

    Config:
        code: str (Python code to execute, uses {input} as variable)
        imports: list[str] (additional imports)
        timeout: int (seconds)
    """

    async def execute(self, context: dict[str, Any]) -> NodeResult:
        code_template = self.config.get("code", "")
        imports = self.config.get("imports", [])
        timeout = self.config.get("timeout", 10)

        input_data = context.get("_last_result", {}).get("data", "")
        code = code_template.replace("{input}", repr(input_data))

        # Add imports
        import_lines = "\n".join(f"import {imp}" for imp in imports)
        full_code = f"{import_lines}\n\n{code}"

        log.info(f"[Workflow:{self.node_id}] Kod çalıştırılıyor...")

        try:
            import sys
            import sys
            import tempfile
            import os
            import subprocess

            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(full_code)
                if "result" in full_code:
                    f.write("\n\ntry:\n    print(result)\nexcept NameError:\n    pass\n")
                temp_name = f.name
                
            try:
                res = subprocess.run(
                    [sys.executable, temp_name],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                output = res.stdout.strip()
                if not output and res.stderr:
                    output = res.stderr.strip()
                return NodeResult(
                    data=output,
                    node_id=self.node_id,
                )
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        except Exception as e:
            return NodeResult(
                data="",
                node_id=self.node_id,
                status="error",
                error=str(e),
            )


class ConditionNode(BaseNode):
    """Condition node — evaluates a condition and routes execution.

    Config:
        condition: str (Python expression evaluating to True/False, uses {input})
        true_branch: str (target node if True)
        false_branch: str (target node if False)

    The workflow engine checks a ConditionNode's result to decide routing.
    """

    async def execute(self, context: dict[str, Any]) -> NodeResult:
        condition_expr = self.config.get("condition", "True")
        input_data = context.get("_last_result", {}).get("data", "")

        # Evaluate condition safely via subprocess
        try:
            import sys
            import subprocess
            code = f"""
input_data = {repr(input_data)}
decision = bool({condition_expr})
print(str(decision).lower())
"""
            res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                raise ValueError(f"Koşul hatası: {res.stderr.strip()}")
            decision = str(res.stdout).strip()
            log.info(f"[Workflow:{{self.node_id}}] Koşul: {{condition_expr}} -> {{decision}}")
            return NodeResult(
                data=decision,
                node_id=self.node_id,
            )
        except Exception as e:
            log.error(f"[Workflow:{self.node_id}] Koşul hatası: {e}")
            return NodeResult(
                data="false",
                node_id=self.node_id,
                status="error",
                error=str(e),
            )


class LoopNode(BaseNode):
    """Loop node — repeats a subgraph of nodes.

    Config:
        max_iterations: int (max loop count)
        until_condition: str (Python expression to stop, uses {input})
        loop_nodes: list[str] (node IDs to include in the loop body)
        exit_node: str (node ID to jump to when condition met)
    """

    async def execute(self, context: dict[str, Any]) -> NodeResult:
        max_iterations = self.config.get("max_iterations", 5)
        until_condition = self.config.get("until_condition", "False")
        exit_node = self.config.get("exit_node", "")

        log.info(f"[Workflow:{self.node_id}] Döngü başlıyor (max {max_iterations})")

        for i in range(max_iterations):
            input_data = context.get("_last_result", {}).get("data", "")

            # Check exit condition safely via subprocess
            try:
                import sys
                import subprocess
                code = f"""
input_data = {repr(input_data)}
iteration = {i}
should_stop = bool({until_condition})
print(should_stop)
"""
                res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=5)
                should_stop = str(res.stdout).strip() == "True"
                if should_stop:
                    log.info(f"[Workflow:{{self.node_id}}] Döngü durdu (iterasyon {{i}})")
                    break
            except Exception:
                pass

            log.info(f"[Workflow:{self.node_id}] Döngü iterasyon {i+1}/{max_iterations}")

            # Store loop iteration info in context for loop body nodes
            context["_loop_iteration"] = i
            context["_loop_node_id"] = self.node_id

            # The workflow engine will re-execute child nodes
            # Return signal to continue looping
            return NodeResult(
                data=f"loop_iteration_{i}",
                node_id=self.node_id,
            )

        # Loop complete
        log.info(f"[Workflow:{self.node_id}] Döngü tamamlandı")
        return NodeResult(
            data="loop_complete",
            node_id=self.node_id,
        )


class TerminalNode(BaseNode):
    """Shell command execution node.

    Config:
        command: str (shell command, uses {input})
        timeout: int (seconds)
    """

    async def execute(self, context: dict[str, Any]) -> NodeResult:
        command_template = self.config.get("command", "")
        timeout = self.config.get("timeout", 30)

        input_data = context.get("_last_result", {}).get("data", "")
        command = command_template.replace("{input}", str(input_data))

        log.info(f"[Workflow:{self.node_id}] Komut: {command[:100]}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout or result.stderr
            return NodeResult(
                data=output.strip(),
                node_id=self.node_id,
                status="success" if result.returncode == 0 else "error",
                error=result.stderr if result.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            return NodeResult(
                data="",
                node_id=self.node_id,
                status="error",
                error=f"Command timed out ({timeout}s)",
            )
        except Exception as e:
            return NodeResult(
                data="",
                node_id=self.node_id,
                status="error",
                error=str(e),
            )


class SleepNode(BaseNode):
    """Pause execution for a given duration.

    Config:
        seconds: int (sleep duration)
    """

    async def execute(self, context: dict[str, Any]) -> NodeResult:
        seconds = self.config.get("seconds", 1)
        log.info(f"[Workflow:{self.node_id}] Bekleniyor ({seconds}s)...")
        await asyncio.sleep(seconds)
        return NodeResult(data=f"slept_{seconds}s", node_id=self.node_id)
