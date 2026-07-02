# Dorina Agent

**Self-hosted CLI AI agent** — terminal tabanli, moduler, aksiyon odakli.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-232%20passed-brightgreen)
![Lines](https://img.shields.io/badge/code-20K%20lines-blue)

> ~20K satir, her satir calisiyor. Gelecek planlari icin `FUTURE.md`'ye bak.

## Features

- **Aktif Toolset Sistemi** — goreve gore 7-16 tool, kategorilerle yonet (tools_enable)
- **MCP Client (Model Context Protocol)** — harici MCP sunucularina baglan, tool'larini kullan
- **State Machine** — 9 durumlu deterministic agent loop
- **Multi-Provider** — DeepSeek, Groq, OpenRouter, Ollama (fallback zincirli)
- **Mod Sistemi** — `/godmode`, `/audit`, `/speed`, `/temp` (sadece prompt degistirir, algoritma ayni)
- **Approval Sistemi** — 3 katmanli: always_allow → needs_approval → hardline block
- **Live Status Bar** — prompt_toolkit toolbar, input alanina dokunmaz
- **Session Management** — sifreli SQLite, save/load/export, otomatik archive
- **Background Tasks** — long-running komutlar (sudo, tcpdump) arkada calisir, bitince bildirim
- **Context Compression** — buyuk konusmalarda otomatik ozetleme
- **Token Budget** — `/budget N` ile limit koy, asilinca compress + uyar
- **Sub-Agent System** — paralel task delegation (SubAgent + batch)
- **Event Bus** — pub/sub ile mod degisiklikleri UI'a aninda yansir
- **Tool Limitsiz** — akilli tool secimi sayesinde tur basi tool limiti yok

## Quick Start

```bash
git clone https://github.com/atalhatulu/dorina-agent.git
cd dorina-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# API key'i ~/.dorina/providers.json'a ekle
python main.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Help |
| `/godmode` | Sinirsiz mod — reddetme yok |
| `/audit` | Denetim modu |
| `/speed` | Hizli mod (6 tool, 10 tur, kisa prompt) |
| `/temp` | Kayitsiz mod |
| `/budget N` | Token limiti |
| `/new` | Yeni session |
| `/save <title>` | Session kaydet |
| `/load <id>` | Session yukle |
| `/session prune [N]` | Eski mesajlari temizle |
| `/session archive [gun]` | Eski session'lari arsivle |
| `/session size` | Session boyutunu goster |

## Architecture

```
dorina-agent/
├── core/              # Config, constants, logger, event bus, mode manager
├── orchestrator/      # State machine, agent loop, reasoning, context
├── providers/         # Multi-model router with fallback
├── tools/             # Registry, executor, 10+ built-in tools
│   ├── builtin/       # terminal, file_tools, web_tools, cron, memory, bg_task
│   ├── mcp/           # MCP client (connection, tool discovery, call, status)
│   ├── toolset.py     # Active toolset manager (kategori sistemi)
│   ├── security.py    # is_destructive(), hardline block
│   └── executor.py    # Hook pipeline (approval, metrics)
├── ui/                # Terminal UI (prompt_toolkit + Rich)
├── commands/          # Slash commands (/godmode, /speed, ...)
├── session/           # Sifreli SQLite session manager
├── security/          # Approval, auth
├── hooks/             # Pre/post execution pipeline
├── soul/              # Personality system
├── knowledge/         # Web search, deep research
├── memory/            # Semantic, episodic, procedural memory
├── skills/            # Skill management
├── tests/             # 232 tests
└── FUTURE.md          # Ideas for next versions (NOT in codebase)
```

## Tests

```bash
source .venv/bin/activate
pytest tests/ -q --tb=short
# 232 passed
```

## Key Design Decisions

- **Core first**: modlar prompt degistirir, algoritmayi degil. Ayni arac secimi, ayni pruning, ayni sudo mantigi her modda calisir.
- **Plan → kod → denetle**: asla plansiz kod yazilmaz. Subagent writer + reviewer paralel calisir.
- **FUTURE.md disiplini**: "ileride lazim olur" diye kod eklenmez. FUTURE.md'ye yazilir, gerektiginde ordan alinir.
- **20K-25K bandi**: yeni ozellik eklenirken eski, az kullanilan silinir. Proje sismez, donusur.

## Credits

Built with inspiration from:
- **Hermes Agent** — tool architecture, session management, state machine
- **Claude Code** — file history, task system
- **Superpowers** — skills/workflows

## License

MIT
