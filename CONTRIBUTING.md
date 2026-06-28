# Contributing to Dorina Agent

Thank you for your interest in contributing! Dorina Agent is a self-hosted CLI AI
agent built with inspiration from Hermes, Claude Code, Odysseus, Superpowers,
and other open-source projects.

> **Note on language:** Dorina Agent is a Turkish project — the codebase,
> internal comments, and variable names are predominantly in Turkish. However,
> all **documentation** (`README.md`, `CONTRIBUTING.md`, `docs/`) must be
> written in **English** for international contributors. When adding new code,
> you may use Turkish for internal strings and comments (as the project does),
> but function signatures and API-facing messages should be self-documenting.

---

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Coding Conventions](#coding-conventions)
- [How to Add a New Tool](#how-to-add-a-new-tool)
- [How to Add a New Module](#how-to-add-a-new-module)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Code Review Guidelines](#code-review-guidelines)

---

## Development Setup

### Prerequisites

- **Python** ≥ 3.10 (3.12+ recommended)
- **Git**
- Optional but recommended:
  - [Playwright](https://playwright.dev/) (for browser tools)
  - [Docker](https://docker.com/) (for sandbox)
  - [Ollama](https://ollama.ai/) (for local LLM)

### Step-by-step

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/dorina-agent.git
cd dorina-agent

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install in editable mode
pip install -e .

# 4. Set up API keys (minimum: DeepSeek)
cp .env.example .env.local
# Edit .env.local with your keys

# 5. Run the agent
./start-dorina.sh
# Or manually:
# python main.py
```

### Verify your setup

```bash
python main.py --version
# Should output: dorina-agent v2.0.0

# Run tests
pytest tests/ -q
# 88+ passed, 0 failed
```

---

## Project Structure

```
dorina-agent/
├── agents/           # Multi-agent & task system
├── browser/          # Playwright web browser client
├── core/             # Config, logger, event bus, constants
├── evolution/        # Self-evolution engine (pattern learning, code audit)
├── export/           # Session export (JSON, Markdown, HTML)
├── gateway/          # FastAPI REST API gateway
├── history/          # File history (snapshot/restore/diff)
├── knowledge/        # Web search, deep research, RAG engine
├── memory/           # Working, episodic, semantic, procedural memory
├── monitoring/       # Metrics & cost tracking
├── orchestrator/     # Agent loop, reasoning, context, state machine
├── providers/        # Multi-model router with fallback
├── security/         # Approval, auth, sandbox
├── session/          # Session manager & export
├── skills/           # Skill system (store, manager, learned skills)
├── soul/             # Personality system (soul.md)
├── tools/            # Tool registry, executor, 66+ built-in tools
│   ├── builtin/      # Built-in tool sets (basic, advanced, terminal, modules)
│   ├── mcp/          # MCP (Model Context Protocol) client
│   └── external/     # External tool integrations
├── ui/               # Terminal UI (Rich + prompt-toolkit)
├── tests/            # 88+ tests
├── main.py           # Entry point
├── start-dorina.sh   # One-click launcher
├── config.yaml       # Agent configuration
└── soul.md           # Agent personality file
```

---

## Coding Conventions

### Language

| Context | Language | Example |
|---------|----------|---------|
| Code comments & internal strings | Turkish (TR) | `# Tool kaydet` |
| Docstrings | Turkish (TR) | `"""Tool kayıt sistemi."""` |
| Public documentation | English (EN) | `README.md`, `docs/*` |
| Function/variable names | English (EN) | `def execute_tool():` |
| Git commits | Turkish or English | `feat: yeni tool eklendi` |

### Style

- **Formatting**: Use [ruff](https://docs.astrada.dev/ruff/) (included as dev dep)
- **Indentation**: 4 spaces, no tabs
- **Line length**: 100 characters max
- **Type hints**: Required for all function signatures (use `from __future__ import annotations`)
- **Imports**: Standard library → third-party → local, sorted alphabetically

### Naming

- `snake_case` for functions, methods, variables
- `PascalCase` for classes
- `UPPER_CASE` for constants
- `_private` prefix for internal methods
- Single leading underscore for module-internal functions

### Patterns

- Use `@dataclass` for data containers
- Use `from __future__ import annotations` at top of every module
- Async functions for I/O-bound operations (network, disk, browser)
- Sync functions for CPU-bound operations
- Favor composition over inheritance
- Use the event bus (`core/event_bus.py`) for cross-module communication

---

## How to Add a New Tool

Tools are the primary way Dorina interacts with the world. Each tool is a
function decorated with `@register_tool`.

### Step 1: Choose the right file

| Tool type | File |
|-----------|------|
| Terminal/exec | `tools/builtin/terminal_pro.py` |
| Terminal utility | `tools/builtin/terminal_utils.py` |
| File operations | `tools/builtin/basic.py` |
| Web/browser | `tools/builtin/modules.py` |
| Advanced/system | `tools/builtin/advanced.py` |
| History | `history/tools.py` |
| Evolution | `evolution/tools.py` |
| Agent/task | `agents/task_tools.py` |
| Testing | `tools/tool_test.py` / `tools/tool_verify.py` |

### Step 2: Define the tool

```python
"""My new tool — does something useful."""
from __future__ import annotations
from tools.registry import register_tool


@register_tool(
    name="my_tool",
    description="Short, clear description of what this tool does.",
    parameters={
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "What this parameter does.",
            },
            "param2": {
                "type": "integer",
                "description": "Another parameter.",
                "default": 42,
            },
        },
        "required": ["param1"],
    },
    toolset="my_category",  # e.g. "terminal", "web", "utility"
)
def my_tool(param1: str, param2: int = 42) -> str:
    """Implement the tool logic.

    Args:
        param1: The first parameter.
        param2: The second parameter (default: 42).

    Returns:
        A JSON-serializable string result.
    """
    result = do_something(param1, param2)
    return json.dumps({"result": result}, ensure_ascii=False)
```

### Step 3: Register the import

If your tool is in a new file, add the import in `main.py`:

```python
from my_module import tools  # noqa: F401
```

### Step 4: Test your tool

```bash
# Test the tool directly
python -c "from tools.registry import registry; t = registry.get('my_tool'); print(t.handler('test'))"

# Run full test suite
pytest tests/ -q
```

### Guidelines for good tools

- **Parameters**: Use descriptive names and provide clear JSON schema
- **Error handling**: Return `json.dumps({"error": str(e)})` on failure
- **Async**: Set `is_async=True` by making the handler an async function
- **Validation**: Add `check_fn` to hide tools when dependencies are missing
- **Toolset**: Use a consistent category name for grouping in `/tools`

---

## How to Add a New Module

Modules add new capabilities to Dorina (e.g., a new memory type, a new
provider, a new subsystem).

### Step 1: Create the module structure

```bash
mkdir my_module
touch my_module/__init__.py
touch my_module/tools.py     # If the module exposes tools
touch my_module/engine.py    # Core module logic
```

### Step 2: Implement the module

```python
# my_module/engine.py
"""Engine for my new module."""
from __future__ import annotations
from core.logger import log
from core.event_bus import bus


class MyEngine:
    """Does something new."""

    def __init__(self):
        self._ready = False
        bus.subscribe("app:startup", self._on_startup)

    def _on_startup(self, event: str, **kw):
        log.info("MyModule initialized")
        self._ready = True

    def do_thing(self) -> str:
        return "Hello from MyModule!"


engine = MyEngine()
```

### Step 3: Export tools (optional)

```python
# my_module/tools.py
from __future__ import annotations
from tools.registry import register_tool
from my_module.engine import engine


@register_tool(
    name="my_module_thing",
    description="Does the thing from MyModule.",
    parameters={"type": "object", "properties": {}},
    toolset="my_module",
)
def my_tool() -> str:
    return engine.do_thing()
```

### Step 4: Integrate in main.py

```python
from my_module import engine    # noqa: F401 — triggers event subscription
from my_module import tools     # noqa: F401 — registers tools
```

### Step 5: Add configuration (if needed)

In `config.yaml` or a new section:

```yaml
my_module:
  enabled: true
  setting1: value
```

### Module integration checklist

- [ ] `__init__.py` exists
- [ ] Tools registered via `@register_tool`
- [ ] Event bus subscriptions for lifecycle hooks
- [ ] Configuration added to `config.yaml` if applicable
- [ ] Global singleton exported (e.g., `engine = MyEngine()`)
- [ ] Imported in `main.py` with `# noqa: F401`
- [ ] Tests added in `tests/`

---

## Testing

```bash
# Run all tests
pytest tests/ -q

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing

# Test a specific module
pytest tests/test_modules.py -v

# Verify tools
python main.py -q "run /verify"
```

All new tools and modules should have corresponding tests in `tests/`.

---

## Pull Request Process

### 1. Before you start

- Check [open issues](https://github.com/atalhatulu/dorina-agent/issues)
  for related work
- Discuss significant changes in an issue first
- Keep PRs focused — one feature/fix per PR

### 2. Branch naming

```
feat/my-new-tool       # New feature
fix/bug-description    # Bug fix
docs/update-readme     # Documentation
refactor/module-name   # Code refactoring
test/add-tests         # Tests
```

### 3. Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(tools): add my_tool for doing X
fix(history): restore fails on Windows paths
docs: add contributing guide
refactor(session): extract export logic
test(tools): add tests for my_tool
```

### 4. PR requirements

- [ ] Code follows project conventions
- [ ] Tests pass (`pytest tests/ -q`)
- [ ] New tools/modules include tests
- [ ] Documentation updated (if applicable)
- [ ] No new linting errors (`ruff check .`)
- [ ] PR description explains what and why

### 5. PR title format

```
type(scope): brief description
```

Examples:
- `feat(tools): add convert_image tool`
- `fix(browser): handle timeout in navigate`
- `docs(architecture): add system overview`

### 6. Review process

1. Automated checks run (tests, lint)
2. Maintainer reviews within 2-3 business days
3. Address review feedback
4. Squash-merge into `main`

---

## Code Review Guidelines

### For reviewers

- Check for type safety and error handling
- Verify the tool follows `@register_tool` conventions
- Ensure new modules integrate via the event bus
- Confirm documentation is updated
- Look for Turkish/English consistency

### For contributors

- Be responsive to feedback
- Explain design decisions in PR comments
- Keep PRs small and reviewable (< 400 lines preferred)
- Mark work-in-progress with draft PR status

---

## Getting Help

- Open an [issue](https://github.com/atalhatulu/dorina-agent/issues)
- Ask in PR comments
- Check existing documentation in `docs/`

---

*Thank you for contributing to Dorina Agent!*
