# Dorina Agent Setup Guide

> **Version:** 1.0.0
> **Python:** 3.10+ required (3.14 recommended)
> **OS:** Linux (primary), macOS, WSL

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Install](#quick-install)
- [API Keys](#api-keys)
- [Configuration](#configuration)
- [First Run](#first-run)
- [Usage](#usage)
- [Commands](#commands)
- [Web Dashboard](#web-dashboard)
- [Advanced Setup](#advanced-setup)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| **Python** | 3.10+ | 3.14 recommended; check with `python3 --version` |
| **pip** | Latest | Usually included with Python |
| **Git** | Any | For cloning the repository |

### Optional

| Feature | Required | Install Command |
|---------|----------|-----------------|
| **Browser tools** | Playwright | `pip install playwright && python3 -m playwright install chromium` |
| **Vision/image** | Pillow | Included in full install |
| **Audio (TTS)** | edge-tts | Included in full install |
| **Code sandbox** | Docker | `sudo pacman -S docker` (Arch) or system equivalent |
| **Local LLM** | Ollama | `curl -fsSL https://ollama.com/install.sh \| sh` |
| **Vector search** | ChromaDB | Installed automatically with dependencies |

---

## Quick Install

### Option 1: One-click (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/atalhatulu/dorina-agent.git
cd dorina-agent

# 2. Make the launcher executable
chmod +x start-dorina.sh

# 3. Run — it auto-creates a venv and installs dependencies
./start-dorina.sh
```

The `start-dorina.sh` script does everything automatically:
1. Creates a Python virtual environment (`.venv/`)
2. Installs dependencies via pip (`pip install .`)
3. Installs the `dorina` command to `~/.local/bin/dorina`
4. Launches the agent

### Option 2: Curl one-liner

```bash
curl -fsSL https://raw.githubusercontent.com/atalhatulu/dorina-agent/main/install.sh | bash
```

Installs to `~/.dorina/` (override with `DORINA_DIR`), creates the venv,
adds the `dorina` command to your PATH, and copies the config template.
Then just run `dorina`.

### Option 3: Manual Install

```bash
# 1. Clone
git clone https://github.com/atalhatulu/dorina-agent.git
cd dorina-agent

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install
pip install -e .

# 4. Run
python main.py
```

---

## API Keys

Dorina stores all provider metadata, API keys, and model lists in a single
file: **`~/.dorina/providers.json`**. The `/setup` wizard fills this file for
you. A project-root `.env` file is an optional override for development.

### Quick key setup

```bash
cp .env.example .env
# Edit .env with your API keys (only needed if you don't use /setup)
```

### Where to get keys

| Provider | Cost | Get Key |
|----------|------|---------|
| **DeepSeek** 🏆 | Free tier available | https://platform.deepseek.com/api_keys |
| **Groq** | Free tier (very fast) | https://console.groq.com/keys |
| **OpenRouter** | Pay-per-use (200+ models) | https://openrouter.ai/keys |
| **OpenAI** | Paid | https://platform.openai.com/api-keys |
| **Anthropic** | Paid | https://console.anthropic.com/ |
| **Google/Gemini** | Free tier | https://aistudio.google.com/ |
| **Ollama** | Free (local) | No key required — `ollama pull llama3` |

### .env format

```bash
# Required: at least one provider key
DEEPSEEK_API_KEY=sk-...
OPENROUTER_API_KEY=sk-...
GROQ_API_KEY=gsk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Optional: HuggingFace token (for model download)
HF_TOKEN=

# MCP: GitHub integration (fine-grained PAT, Contents: read-only, Issues/PRs: write)
# https://github.com/settings/tokens?type=beta
GITHUB_TOKEN=
```

> **Security note:** `.env` is in `.gitignore` and will not be committed.
> Keep your API keys private and never share them.

---

## Configuration

### Where is the config?

The **single source of truth** is `~/.dorina/config.yaml` (DORINA_HOME).
The project-root `config.yaml.example` is just a template: on first run,
`ensure_dorina_home()` copies it to `~/.dorina/config.yaml` if it doesn't
exist yet.

All user data lives under `~/.dorina/`:

| Path | Purpose |
|------|---------|
| `~/.dorina/config.yaml` | Model, tools, security, UI settings (single source of truth) |
| `~/.dorina/providers.json` | API keys + provider metadata |
| `~/.dorina/setup.json` | Setup wizard output |
| `~/.dorina/data/sessions.db` | Session database |
| `~/.dorina/sessions/` | Exported sessions (md/archive) |
| `~/.dorina/skills/` | Learned skills |
| `~/.dorina/SOUL.md` | Personality file |

### Key sections of config.yaml

```yaml
# ─── Model Configuration ───
model:
  default: deepseek/deepseek-v4-flash    # Primary model
  provider: deepseek                     # Provider name
  fallback_providers:                    # Backup providers (in order)
    - openrouter/openai/gpt-4o-mini
    - ollama/llama3
  context_length: 128000                 # Max context tokens
  max_tokens: 4096                       # Max response tokens

# ─── Session Configuration ───
session:
  auto_save: true                        # Auto-save after every exchange
  max_sessions: 100
  storage: sqlite

# ─── Security Configuration ───
security:
  always_allow:                          # Tools that run without confirmation
    - read_file
    - search_files
    - web_search
  ask_always:                            # Tools that always ask permission
    - delete_file
    - rm
    - execute_code
  redact_secrets: true                   # Mask secrets in output
  block_destructive_commands: true

# ─── UI Configuration ───
terminal:
  markdown: true
  status_bar: true
  theme: dark

# ─── Soul / Personality ───
soul:
  file: soul.md
  language: tr                           # Language (tr or en)

# ─── Tools ───
tools:
  approval_mode: smart
  mcp_enabled: true
  sandbox: docker                        # none | docker
```

### Key settings to customize

1. **Model**: Change `model.default` in `~/.dorina/config.yaml`
2. **Fallbacks**: Add/remove providers in `model.fallback_providers`
3. **Language**: Set `soul.language` to `tr` or `en`
4. **Auto-save**: Toggle `session.auto_save`
5. **Security**: Customize `always_allow` and `ask_always` lists

> Model/provider değişikliği `~/.dorina/config.yaml` üzerinden yapılır,
> proje kökündeki `config.yaml` DEĞİL.

---

## First Run

### Automatic Setup Wizard

On the **very first run**, Dorina automatically launches the `/setup` wizard:

```
┌───────────────────────────────────────────────┐
│           Dorina Agent Setup                   │
│                                               │
│  Configure your agent. All settings saved     │
│  to ~/.dorina/                                │
└───────────────────────────────────────────────┘

Step 1: Select Provider
  Available: deepseek, groq, openrouter, ollama, ...

Step 2: Enter API Key
  (securely stored in ~/.dorina/providers.json)

Step 3: Select Model
  (varies by provider)

Step 4: Preferences
  Language: tr/en
  Show status bar? (Y/n)
```

The wizard will:
1. Prompt you to select an LLM provider
2. Ask for your API key (entered securely, not echoed)
3. Let you pick a model from the available options
4. Configure language and UI preferences
5. Save settings to `~/.dorina/setup.json` and update `~/.dorina/config.yaml`

### Manual setup

If you prefer, you can configure everything manually before running:

```bash
# 1. Edit ~/.dorina/config.yaml with your model preferences
# 2. Create .env with your API keys
# 3. Run
python main.py
```

### Re-run setup anytime

```
/setup
```

Type `/setup` at any time to re-run the setup wizard.

---

## Usage

### Interactive Mode

```bash
./start-dorina.sh
# or
python main.py
# or (global command)
dorina
```

This starts the interactive REPL. Type your questions, requests, or commands
at the `>` prompt.

### Single Query Mode

```bash
python main.py -q "What is the weather in Istanbul?"
```

Useful for automation, scripts, or quick questions.

### New Session

```bash
python main.py --new
```

### Check Version

```bash
python main.py --version
# Output: dorina-agent v1.0.0
```

---

## Commands

### Interactive commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/tools` | List all registered tools |
| `/status` | Show current session status |
| `/model` | Change model (opens wizard) |
| `/setup` | Re-run setup wizard |
| `/new` | Start a new session |
| `/save <title>` | Save current session |
| `/load <id>` | Load a saved session |
| `/sessions` | List all sessions |
| `/ara <query>` | Search sessions (Turkish: "ara") |
| `/skills` | List learned skills |
| `/personality` | Show current personality (soul.md) |
| `/godmode` | Unlimited mode — no refusals |
| `/audit` | Audit mode |
| `/speed` | Fast mode (6 tools, 10 turns, short prompt) |
| `/temp` | No-save mode |
| `/budget N` | Set token budget |
| `/session prune [N]` | Clean old messages |
| `/session archive [gun]` | Archive old sessions |
| `/session size` | Show session size |
| `/verify` | Verify all tools |
| `/verify <name>` | Verify a specific tool |
| `/export json` | Export session as JSON |
| `/export md` | Export session as Markdown |
| `/export html` | Export session as HTML |
| `/clear` | Clear terminal screen |
| `/exit` | Exit Dorina Agent |

### CLI flags

| Flag | Description |
|------|-------------|
| `-q "query"` / `--query "query"` | Single query mode |
| `--new` | Start a new session |
| `--version` | Show version and exit |

---

## Web Dashboard

Dorina has a local web dashboard (session management, tool steps, token/cost,
thinking panel):

```bash
python -m gateway.app
# Dashboard → http://localhost:5792
```

Local only (127.0.0.1), no cloud.

---

## Advanced Setup

### Full installation (all features)

```bash
# 1. Clone and install
git clone https://github.com/atalhatulu/dorina-agent.git
cd dorina-agent
python3 -m venv .venv
source .venv/bin/activate

# 2. Install all dependencies
pip install -e ".[full]"

# 3. Install browser support
pip install playwright
python3 -m playwright install chromium

# 4. Set up Docker sandbox (optional)
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect

# 5. Set up local LLM (optional)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3

# 6. Run
python main.py
```

### Global `dorina` command

The `start-dorina.sh` script automatically installs the `dorina` command to
`~/.local/bin/`. After running it once, you can launch Dorina from anywhere:

```bash
dorina                    # Interactive mode
dorina -q "hello"         # Single query
dorina --new              # New session
dorina --version          # Version info
```

### Docker sandbox

For safe code execution, Dorina can run tools inside a Docker container:

```yaml
# ~/.dorina/config.yaml
tools:
  sandbox: docker
```

The sandbox uses the Docker image `python:3.12-slim` with opt-out for
individual tools.

### MCP (Model Context Protocol)

MCP integration allows Dorina to connect to MCP servers for additional
capabilities:

```yaml
# ~/.dorina/config.yaml
tools:
  mcp_enabled: true
  mcp_servers:
    - name: github
      command: npx
      args: ["-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_TOKEN: $GITHUB_TOKEN
```

MCP tools are auto-discovered and registered on startup.

---

## Troubleshooting

### "Python 3.10 not found"

Dorina requires Python 3.10+. If you have an older version:

```bash
# Arch/Manjaro
sudo pacman -S python3

# Ubuntu/Debian
sudo apt update && sudo apt install python3 python3-venv python3-pip

# macOS
brew install python@3.12
```

### "ModuleNotFoundError: No module named 'litellm'"

Core dependencies are not installed:

```bash
source .venv/bin/activate
pip install -e .
```

Or let `start-dorina.sh` handle it.

### "API key not found" / "Provider error"

1. Check that `~/.dorina/providers.json` exists and has valid keys
   (or run `/setup` to fill it interactively)
2. Ensure the provider name in `~/.dorina/config.yaml` matches your key
3. Check your API key balance/status on the provider website

### "Playwright browser not found"

```bash
pip install playwright
python3 -m playwright install chromium
```

### "Docker not found" (when sandbox enabled)

Either install Docker or disable the sandbox:

```yaml
# ~/.dorina/config.yaml
tools:
  sandbox: none   # Disable Docker sandbox
```

### "Connection refused: Ollama"

Ollama is not running:

```bash
ollama serve     # Start Ollama server
ollama pull llama3  # Pull a model
```

### "Session database locked"

If you get SQLite locking errors:

```bash
rm ~/.dorina/data/sessions.db   # Reset session database
# Warning: This deletes all saved sessions
```

### Reset everything

```bash
# Remove virtual environment
rm -rf .venv/

# Remove setup configuration
rm -rf ~/.dorina/

# Reinstall and reconfigure
./start-dorina.sh
```

---

## Getting Help

- **Issues**: https://github.com/atalhatulu/dorina-agent/issues
- **Documentation**: See `docs/` directory
- **Built-in help**: Type `/help` in the agent
- **Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md)

---

*Happy building with Dorina Agent!*
