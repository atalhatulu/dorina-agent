"""Workflow tool — run_workflow ile agent workflow baslatir."""
from __future__ import annotations
import json
from pathlib import Path

from tools.registry import register_tool


@register_tool(
    name="run_workflow",
    description="Bir workflow'u calistir. workflow_name: workflows/altindaki .yaml veya .json dosyasinin adi (uzantisiz). "
                "Ornek: 'code-review' → workflows/code-review.yaml",
    parameters={
        "type": "object",
        "properties": {
            "workflow_name": {
                "type": "string",
                "description": "Workflow adi (uzantisiz). Ornekler: code-review, deploy, test-runner",
            },
            "input_data": {
                "type": "string",
                "description": "Workflow'a gonderilecek input (opsiyonel)",
                "default": "",
            },
        },
        "required": ["workflow_name"],
    },
    toolset="default",
)
async def run_workflow_tool(workflow_name: str, input_data: str = "") -> str:
    """Bir workflow'u adina gore bulup calistirir."""
    workflow_dir = Path(__file__).resolve().parent.parent.parent / "workflows"
    
    # Workflow dosyasini ara (.yaml veya .json)
    wf_path = None
    for ext in [".yaml", ".yml", ".json"]:
        candidate = workflow_dir / f"{workflow_name}{ext}"
        if candidate.exists():
            wf_path = candidate
            break
    
    if not wf_path:
        # workflows/ altinda mevcut workflow'lari listele
        available = []
        for f in sorted(workflow_dir.glob("*.yaml")) + sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.json")):
            available.append(f.stem)
        msg = f"Workflow bulunamadi: '{workflow_name}'"
        if available:
            msg += f". Mevcut workflow'lar: {', '.join(available)}"
        return json.dumps({"error": msg})
    
    try:
        from workflows.engine import WorkflowEngine
        from workflows.graph import WorkflowGraph
        
        engine = WorkflowEngine()
        
        # Workflow dosyasindan graph olustur
        if wf_path.suffix in (".yaml", ".yml"):
            import yaml
            graph_data = yaml.safe_load(wf_path.read_text())
        else:
            graph_data = json.loads(wf_path.read_text())
        
        graph = WorkflowGraph.from_dict(graph_data) if hasattr(WorkflowGraph, 'from_dict') else WorkflowGraph()
        if not hasattr(WorkflowGraph, 'from_dict'):
            # Manuel graph olustur (fallback)
            for step in graph_data.get("steps", []):
                graph.add_node(
                    step.get("id", ""),
                    step.get("action", "llm"),
                    step.get("prompt", ""),
                    deps=step.get("deps", []),
                )
        
        result = await engine.run(graph, input_data=input_data)
        
        return json.dumps({
            "success": True,
            "workflow": workflow_name,
            "execution_id": result.execution_id,
            "status": result.status,
            "result": str(result.result)[:1000] if result.result else "",
            "steps_completed": len(result.completed_steps) if hasattr(result, 'completed_steps') else 0,
        }, ensure_ascii=False)
    
    except Exception as e:
        return json.dumps({"error": f"Workflow hatasi: {str(e)}"})
