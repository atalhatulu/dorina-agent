"""Clarify tool — kullaniciya soru sor, cevap al."""
from __future__ import annotations
import json

from tools.registry import register_tool


@register_tool(
    name="clarify",
    description="Kullaniciya bir soru sor ve cevap bekle. Sadece emin olmadigin durumlarda kullan (dosya silme, geri alinamaz islem, net olmayan talimat). Her seferinde sorma, once kendin karar ver.",
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Kullaniciya sorulacak soru. Acik ve net ol."},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Opsiyonel secenekler (ornek: ['y', 'n'] veya ['devam', 'iptal'])",
            },
        },
        "required": ["question"],
    },
    toolset="communication",
)
def clarify_tool(question: str, options: list[str] | None = None) -> str:
    """Kullaniciya soru sor, cevap al."""
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
        return json.dumps({"success": False, "answer": "", "question": question, "error": "Kullanici cevap vermedi"})
