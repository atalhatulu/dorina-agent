"""Clarify tool — ask user a question, get answer."""
from __future__ import annotations
import json

from tools.registry import register_tool


@register_tool(
    name="clarify",
    description="Ask the user a question and wait for an answer. Only use when uncertain (file deletion, irreversible operations, unclear instructions). Do NOT ask every time — decide first.",
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Question to ask the user. Be clear and specific."},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional options (e.g., ['y', 'n'] or ['continue', 'cancel'])",
            },
        },
        "required": ["question"],
    },
    toolset="communication",
)
def clarify_tool(question: str, options: list[str] | None = None) -> str:
    """Ask user a question, get answer."""
    from rich.console import Console
    console = Console()
    console.print()
    console.print(f"  [bold #D4622A]?[/bold #D4622A] [italic]{question}[/italic]")
    if options:
        opt_str = " ("
        opt_str += "/".join(options)
        opt_str += ")"
        console.print(f"    [dim]{opt_str}[/dim]")
    try:
        answer = input("  > ").strip()
        return json.dumps({"success": True, "answer": answer, "question": question})
    except (EOFError, KeyboardInterrupt):
        return json.dumps({"success": False, "answer": "", "question": question, "error": "User did not respond"})
