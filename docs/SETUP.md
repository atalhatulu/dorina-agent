# Dorina Agent Setup Guide

> **Version:** 2.0.0  
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

### Check your Python version

```bash
python3 --version
# Should be Python 3.10.x or higher
```

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
2. Installs core dependencies via pip
3. Installs the `dorina` command to `~/.local/bin/dorina`
4. Launches the agent

### Option 2: Manual Install

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

### Option 3: Desktop Shortcut

Double-click `dorina-agent.desktop` on your desktop (auto-created during setup).

---

## API Keys

Dorina Agent requires API keys for LLM access. At minimum, you need a
**DeepSeek** API key.

### Quick key setup

Copy the example env file and fill in your keys:

```bash
cp .env.example .env.local
# Edit .env.local with your API keys
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

### .env.local format

```bash
# Primary: DeepSeek (recommended — free tier available)
DEEPSEEK_API_KEY=sk-your-deepseek-key-here

# Backup: Groq (free, very fast)
GROQ_API_KEY=gsk_your-groq-key

# Backup: OpenRouter (200+ models)
OPENROUTER_API_KEY=sk-or-your-key-here

# Local: Ollama (no key needed)
OLLAMA_HOST=http://localhost:11434

# Email (optional — for send_email tool)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_ADDR=your@email.com
EMAIL_PASS=your-app-password
```

> **Security note:** `.env.local` is in `.gitignore` and will not be committed.
> Keep your API keys private and never share them.

---

## Configuration

### config.yaml

All agent settings are in `config.yaml` at the project root. Key sections:

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
  max_sessions: 100                      # Max stored sessions
  storage: sqlite                        # Storage backend

# ─── Memory Configuration ───
memory:
  enabled: true
  vector_store: chroma
  embedding_model: BAAI/bge-small-en-v1.5
  max_working_messages: 20
  auto_extract: true                     # Auto-extract knowledge

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
  markdown: true                         # Enable markdown rendering
  status_bar: true                       # Show live status bar
  theme: dark                            # UI theme

# ─── Soul / Personality ───
soul:
  file: soul.md                          # Personality file path
  language: tr                           # Language (tr or en)

# ─── Skills ───
skills:
  auto_detect: true
  enabled: true
  store_dir: skills/store

# ─── Tools ───
tools:
  approval_mode: smart
  mcp_enabled: true
  sandbox: docker
```

### Key settings to customize

1. **Model**: Change `model.default` to your preferred model
2. **Fallbacks**: Add/remove providers in `model.fallback_providers`
3. **Language**: Set `soul.language` to `tr` or `en`
4. **Auto-save**: Toggle `session.auto_save` based on preference
5. **Security**: Customize `always_allow` and `ask_always` lists

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
  (securely stored in ~/.dorina/)

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
5. Save settings to `~/.dorina/setup.json` and update `config.yaml`

### Manual setup

If you prefer, you can configure everything manually before running:

```bash
# 1. Edit config.yaml with your model preferences
# 2. Create .env.local with your API keys
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
# Output: dorina-agent v2.0.0
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
# config.yaml
tools:
  sandbox: docker
```

The sandbox uses the Docker image `python:3.12-slim` with opt-out for
individual tools.

### MCP (Model Context Protocol)

MCP integration allows Dorina to connect to MCP servers for additional
capabilities:

```yaml
# config.yaml
tools:
  mcp_enabled: true
```

MCP tools are auto-discovered and registered on startup.

---

## Troubleshooting

### "Python 3.14 not found"

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

1. Check that `.env.local` exists and has valid keys
2. Ensure the provider name in `config.yaml` matches your key
3. Run `/setup` to configure keys interactively
4. Check your API key balance/status on the provider website

### "Playwright browser not found"

```bash
pip install playwright
python3 -m playwright install chromium
```

### "Docker not found" (when sandbox enabled)

Either install Docker or disable the sandbox:

```yaml
# config.yaml
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
rm data/sessions.db   # Reset session database
# Warning: This deletes all saved sessions
```

### Reset everything

```bash
# Remove virtual environment
rm -rf .venv/

# Remove setup configuration
rm -rf ~/.dorina/

# Remove session database
rm -f data/sessions.db

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
