# Dorina Agent — API Reference

> Comprehensive documentation of all 66+ tools available in Dorina Agent.

---

## Overview

Dorina Agent exposes tools organized into **toolsets** (categories). Each tool has a unique name, description, parameters (JSON Schema), and a handler function. This document lists every registered tool with its purpose and parameters.

**Toolsets:** terminal, file, web, utility, system, browser, delegation, development, communication, vision, agent, history, evolution, tasks, mcp, research

---

## 🖥️ Terminal Tools

### `terminal`
Execute shell commands and return output.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | string | *required* | Command to execute |
| `timeout` | integer | 30 | Timeout in seconds |

**Toolset:** terminal

---

## 📁 File Tools

### `read_file`
Read a file's content with line numbers. Searches broadly if exact path not found (CWD, home, Downloads, Desktop, Documents).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | File path |
| `limit` | integer | 200 | Max lines to show |

**Toolset:** file

---

### `write_file`
Write content to a file. Creates parent directories if needed. Auto-snapshots via file history.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | File path |
| `content` | string | *required* | Content to write |

**Toolset:** file

---

### `search_files`
Search inside files or by file name. Uses `find` for name matching, `grep` for content matching. Broad search across home directory when path is ".".

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | string | *required* | Search pattern |
| `path` | string | "." | Directory to search |
| `file_glob` | string | "" | File filter (e.g., *.py) |

**Toolset:** file

---

### `patch`
Find-and-replace in a file. Supports dry-run preview.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | File path |
| `old_string` | string | *required* | Text to find |
| `new_string` | string | *required* | Replacement text |
| `dry_run` | boolean | false | Preview without writing |

**Toolset:** file

---

## 🌐 Web Tools

### `web_search`
Web search using DuckDuckGo. Supports safe search and language filtering.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *required* | Search query |
| `max_results` | integer | 5 | Max results |
| `safe_search` | boolean | true | Safe search filter |
| `language` | string | "" | Language filter (e.g., tr, en, de) |

**Toolset:** web

---

### `web_search_multi`
Multi-source web search (aggregates from multiple search engines).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *required* | Search query |
| `max_results` | integer | 5 | Max results |

**Toolset:** web

---

### `web_fetch`
Fetch content from a URL. Supports custom method, headers, CSS selectors, and text extraction.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | *required* | URL to fetch |
| `max_size` | integer | 5000 | Max characters (max 100000) |
| `extract_text` | boolean | true | Extract text from HTML |
| `css_selector` | string | "" | CSS selector for targeted extraction |
| `headers` | string | "" | Custom HTTP headers (JSON string) |
| `timeout` | integer | 15 | Timeout in seconds |
| `raw` | boolean | false | Return raw content without parsing |
| `method` | string | "GET" | HTTP method (GET, POST, etc.) |
| `data` | string | "" | POST request body |

**Toolset:** web

---

## 🧰 Utility Tools

### `clipboard_copy`
Copy text to clipboard. Supports multi-line text. Falls back to xclip if pyperclip unavailable.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | *required* | Text to copy (multi-line) |

**Toolset:** utility

---

### `clipboard_paste`
Read text from clipboard. Truncates at 2000 characters with a warning.

*No parameters required.*

**Toolset:** utility

---

### `tree`
Display directory structure as a tree. Supports file size and exclusion patterns.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | "." | Starting directory |
| `depth` | integer | 2 | Tree depth |
| `show_size` | boolean | false | Show file sizes |
| `exclude` | string | "" | Exclusion patterns (e.g., node_modules,.git) |

**Toolset:** utility

---

### `diff`
Show differences between two files. Supports unified and side-by-side modes.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file1` | string | *required* | First file |
| `file2` | string | *required* | Second file |
| `side_by_side` | boolean | false | Side-by-side display mode |

**Toolset:** utility

---

### `system_info`
Display system information: CPU, RAM, disk, OS, uptime, load average, GPU.

*No parameters required.*

**Toolset:** utility

---

### `hash`
Calculate file hash. Supports MD5, SHA1, SHA256, SHA512.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | File path |
| `algorithm` | string | "sha256" | Hash algorithm (md5, sha1, sha256, sha512) |

**Toolset:** utility

---

### `backup`
Create a timestamped file backup (`.bak` or dated).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | File to backup |
| `dated` | boolean | false | Add date to filename |

**Toolset:** utility

---

### `head`
Show the first N lines of a file. Searches broadly if exact path not found.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | File path |
| `lines` | integer | 10 | Number of lines |
| `line_numbers` | boolean | false | Show line numbers |

**Toolset:** utility

---

### `tail`
Show the last N lines of a file. Supports follow mode and line numbers.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | File path |
| `lines` | integer | 10 | Number of lines |
| `show_numbers` | boolean | false | Show line numbers |
| `follow` | boolean | false | Follow mode (-f, blocks process) |

**Toolset:** utility

---

### `count`
Count lines, words, and characters in a file. Optional regex pattern filtering.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | File path |
| `pattern` | string | "" | Only count lines matching this regex |

**Toolset:** utility

---

### `json_pretty`
Display JSON text formatted. Supports syntax highlighting and minification.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | *required* | JSON text or file path |
| `syntax_highlight` | boolean | false | ANSI color syntax highlighting |
| `minify` | boolean | false | Minified (single-line) output |

**Toolset:** utility

---

### `markdown_preview`
Preview a Markdown file in the terminal. Optional rendered mode with ANSI formatting.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | .md file path |
| `lines` | integer | 30 | Number of lines |
| `render` | boolean | false | Rendered view with ANSI colors |

**Toolset:** utility

---

### `disk_usage`
Show disk usage for a directory. Supports human-readable mode and top-N display.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | "." | Directory path |
| `depth` | integer | 1 | Depth |
| `human_readable` | boolean | true | Human-readable sizes (K/M/G) |
| `top` | integer | 10 | Show top N largest directories (0=all) |

**Toolset:** utility

---

### `uuid_generate`
Generate UUIDs. Supports versions 1, 3, 4, 5, 7. Multiple output formats.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `count` | integer | 1 | Number of UUIDs (max 100) |
| `version` | integer | 4 | UUID version (1, 3, 4, 5, 7) |
| `namespace` | string | "" | Namespace for v3/v5 (DNS, URL, OID, X500) |
| `name` | string | "" | Name for v3/v5 |
| `format` | string | "standard" | Output format (standard, hex, urn, base64) |
| `uppercase` | boolean | false | Uppercase output |

**Toolset:** utility

---

### `timer`
Timer tool: countdown, stopwatch, lap timing.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | string | "countdown" | Mode: countdown, stopwatch, lap |
| `seconds` | integer | 0 | Duration (for countdown) |
| `label` | string | "" | Timer label (for stopwatch/lap) |

**Toolset:** utility

---

### `archive_create`
Create a zip or tar.gz archive of files/directories. Shows compression ratio and timing.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source` | string | *required* | File/directory to archive |
| `format` | string | "zip" | Archive format (zip, tar.gz) |
| `output` | string | "" | Output filename (optional) |

**Toolset:** utility

---

### `archive_extract`
Extract a zip/tar.gz archive.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `archive` | string | *required* | Archive file |
| `dest` | string | "." | Destination directory |

**Toolset:** utility

---

### `ps`
List running processes. Supports sorting (cpu, mem, pid, time) and tree view.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `filter` | string | "" | Name filter (optional) |
| `sort` | string | "mem" | Sort by: cpu, mem, pid, time |
| `tree` | boolean | false | Tree view (ps auxf) |

**Toolset:** utility

---

### `kill`
Terminate a process by PID or name. Supports signal names (SIGTERM, SIGKILL, SIGHUP).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pid` | integer | 0 | Process ID (mutually exclusive with name) |
| `name` | string | "" | Process name (mutually exclusive with pid) |
| `force` | boolean | false | Force kill (-9) |
| `signal_name` | string | "" | Signal name (SIGTERM, SIGKILL, SIGHUP) |

**Toolset:** utility

---

### `find_in_files`
Search for text in files using grep. Supports case-insensitive search and file pattern filtering.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | string | *required* | Search pattern |
| `path` | string | "." | Search directory |
| `file_pattern` | string | "" | File filter (e.g., *.py) |
| `case_insensitive` | boolean | false | Case-insensitive search |
| `max_results` | integer | 30 | Max results |

**Toolset:** utility

---

### `batch_rename`
Batch rename files using simple text replacement or regex.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | Directory |
| `old` | string | *required* | Old text or regex pattern |
| `new` | string | *required* | New text |
| `preview` | boolean | true | Preview only, no changes |
| `dry_run` | boolean | true | Same as preview (backward compat) |
| `use_regex` | boolean | false | Use regex pattern |

**Toolset:** utility

---

### `csv_view`
Display CSV file as a formatted table with column widths.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | CSV file path |
| `rows` | integer | 10 | Number of rows |

**Toolset:** utility

---

### `csv_to_table`
Read CSV file and return as a formatted table.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *required* | CSV file path |

**Toolset:** utility

---

### `weather`
Show weather information via free wttr.in service. Supports forecast and wind details.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `city` | string | "" | City name |
| `forecast` | boolean | false | Show 3-day forecast |
| `wind` | boolean | false | Show wind speed/direction |

**Toolset:** utility

---

### `ping`
Ping a host. Supports count, timeout, and packet size.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | string | *required* | Target address |
| `count` | integer | 3 | Ping count |
| `timeout` | integer | 10 | Timeout in seconds |
| `packet_size` | integer | 56 | Packet size in bytes |

**Toolset:** utility

---

### `dns_lookup`
DNS query using dig/nslookup. Supports A, AAAA, MX, TXT, CNAME record types.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | string | *required* | Host to query |
| `type` | string | "A" | Query type (A, AAAA, MX, TXT, CNAME) |

**Toolset:** utility

---

### `base64_encode`
Encode text or file to base64.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | "" | Text to encode (mutually exclusive with file_path) |
| `file_path` | string | "" | File to encode (mutually exclusive with text) |

**Toolset:** utility

---

### `base64_decode`
Decode base64-encoded text. Supports string or bytes output format.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | *required* | Base64 text to decode |
| `output_format` | string | "str" | Output format: str or bytes |

**Toolset:** utility

---

### `calc`
Calculate mathematical expressions safely using Python AST evaluation.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `expression` | string | *required* | Math expression |

**Supported functions:** +, -, *, /, **, %, sqrt(), abs(), min(), max(), round()

**Toolset:** utility

---

### `convert`
Unit conversion. Supports data (MB/GB), distance (km/mi, inch/cm, foot/meter), weight (kg/lb, ounce/gram), volume (liter/gallon), temperature (C/F/K).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `value` | number | *required* | Value to convert |
| `from_unit` | string | *required* | Source unit |
| `to_unit` | string | *required* | Target unit |

**Toolset:** utility

---

### `git_status`
Show git repository status. Short or detailed mode with branch name.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | "." | Git repo path |
| `mode` | string | "short" | Display mode: short or detail |

**Toolset:** utility

---

### `git_log`
Show recent git commits. Supports author filter and date range.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | "." | Git repo path |
| `count` | integer | 5 | Number of commits |
| `author` | string | "" | Author filter (name or email) |
| `since` | string | "" | Start date (e.g., "2024-01-01") |
| `until` | string | "" | End date (e.g., "2024-12-31") |

**Toolset:** utility

---

### `get_time`
Display current date and time. Supports timezone, output format (ISO, Unix, human), and offset calculations.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timezone` | string | "" | Timezone (e.g., UTC, Europe/Istanbul) |
| `format` | string | "iso" | Output format (iso, unix, human) |
| `add_days` | integer | 0 | Days to add |
| `add_hours` | integer | 0 | Hours to add |

**Toolset:** utility

---

### `list_tools`
List all available tools. Optional toolset filter.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `toolset` | string | "" | Filter by toolset name (e.g., file, web, utility) |

**Toolset:** utility

---

## 🔧 System Tools

### `list_providers`
List available LLM providers (DeepSeek, Groq, Ollama, etc.).

*No parameters required.*

**Toolset:** system

---

### `switch_provider`
Switch the active LLM provider.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | string | *required* | Provider name |

**Toolset:** system

---

## 🧩 Development Tools

### `tool_test`
Test a specific tool with automated prompt generation, validation, retry, and timeout.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tool_name` | string | *required* | Tool name to test |

**Toolset:** development

---

### `tool_test_all`
Test all tools or those in a specific category. Supports parallel execution.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `parallel` | boolean | false | Parallel execution |
| `category` | string | null | Category filter (terminal, file, web, utility, etc.) |

**Toolset:** development

---

### `tool_verify`
End-to-end AI-driven tool verification. Sends natural language prompts to the LLM and verifies tool calls.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tool_name` | string | "" | Tool name to test (empty = all, --reset = clear cache, --list = show status) |

**Toolset:** development

---

### `sandbox_python`
Execute Python code in a secure sandbox environment.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `code` | string | *required* | Python code to execute |

**Toolset:** development

---

### `run_workflow`
Execute a multi-step workflow defined as a list of steps.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `steps` | array | *required* | List of steps: [{"name": "...", "action": "..."}] |

**Toolset:** development

---

## 🌐 Browser Tools

### `browser_navigate`
Navigate to a web page in a browser. Optional screenshot and text extraction.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | *required* | URL to navigate to |
| `screenshot` | boolean | false | Take a screenshot |
| `screenshot_path` | string | "" | Screenshot save path |
| `extract_text` | boolean | false | Extract page text |

**Toolset:** browser

---

## 👥 Delegation Tools

### `delegate_task`
Delegate a task to a sub-agent. Runs asynchronously and returns a summary.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `goal` | string | *required* | Task for the sub-agent |
| `context` | string | "" | Context/information for the sub-agent |

**Toolset:** delegation

---

### `delegate_batch`
Run multiple sub-agents in parallel with different tasks.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tasks` | array | *required* | List of tasks: [{"goal": "...", "context": "..."}] |

**Toolset:** delegation

---

### `run_crew`
Run a multi-agent crew (planner + researcher + writer).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | string | *required* | Task description |

**Toolset:** delegation

---

### `plan_and_execute`
Plan and execute multi-step tasks. Breaks complex requests into sub-tasks.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | string | *required* | Full user request |
| `parallel` | boolean | false | Execute independent steps in parallel |

**Toolset:** agent

---

## 📧 Communication Tools

### `send_email`
Send an email.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `to` | string | *required* | Recipient email |
| `subject` | string | *required* | Subject line |
| `body` | string | *required* | Message body |

**Toolset:** communication

---

## 👁️ Vision Tools

### `analyze_image`
Analyze an image file: format, dimensions, color mode, file size, and EXIF data.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_path` | string | *required* | Image file path (jpg, png, gif, bmp, webp) |

**Toolset:** vision

---

## 🔬 Research Tools

### `deep_research`
Perform deep multi-step web research with iterative searching and synthesis.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `question` | string | *required* | Research question/topic |

**Toolset:** research

---

## 📜 History Tools

### `history`
Show file change history. Lists when and what files changed.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | string | "" | Specific file history (optional) |
| `limit` | integer | 10 | Number of snapshots to show |

**Toolset:** history

---

### `restore`
Restore a file to a previous snapshot.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | string | *required* | File to restore |
| `index` | integer | -1 | Snapshot index (-1 = latest) |

**Toolset:** history

---

### `diff_history`
Show diff between current file and a snapshot.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | string | *required* | File path |
| `index` | integer | -1 | Snapshot index |

**Toolset:** history

---

## 🧬 Evolution Tools

### `self_check`
Scan own codebase, find bugs, detect dead code, and suggest improvements.

*No parameters required.*

**Toolset:** evolution

---

### `self_learn`
Learn from usage patterns and automatically generate skills.

*No parameters required.*

**Toolset:** evolution

---

## 📋 Task Tools

### `task_create`
Create a new task. Types: local_bash, local_agent, local_workflow, monitor.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | string | *required* | Task type |
| `goal` | string | *required* | Task goal / command |

**Toolset:** tasks

---

### `task_list`
List tasks. Optional status filter (pending, running, completed, failed, killed).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | "" | Status filter (optional) |

**Toolset:** tasks

---

### `task_status`
Check the status of a specific task.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task_id` | string | *required* | Task ID |

**Toolset:** tasks

---

## 🔌 MCP Tools

### `mcp_list_tools`
List all tools available on connected MCP servers. (Disabled by default, enabled when MCP configured.)

*No parameters required.*

**Toolset:** mcp

---

### `mcp_call_tool`
Call a tool on an MCP server. (Disabled by default, enabled when MCP configured.)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tool_name` | string | *required* | MCP tool name |
| `arguments` | object | {} | Tool parameters |

**Toolset:** mcp

---

## Summary

- **Total tools:** 66+
- **Toolsets:** terminal, file, web, utility, system, browser, delegation, development, communication, vision, agent, history, evolution, tasks, mcp, research

All tools are registered in `tools/registry.py` via the `@register_tool` decorator and stored in the global `ToolRegistry` instance. Tools can be filtered by toolset and are available to the LLM via JSON Schema function calling.

---

## 🌍 Internationalization (i18n)

Dorina Agent supports **multi-language error messages and UI strings** via a built-in i18n system.

### Language Files

| File | Language |
|------|----------|
| `core/i18n/tr.json` | Türkçe (Turkish) |
| `core/i18n/en.json` | English |

### Configuration

Language is set in `config.yaml`:

```yaml
language: tr  # Default UI language (tr, en)
soul:
  language: tr
```

### Usage

```python
from core.constants import t, set_language, get_language

# Set language
set_language("tr")

# Translate with format variables
msg = t("error_not_found_file", path="/tmp/test.txt")
# Returns: "Dosya bulunamadı: /tmp/test.txt"

msg = t("info_loaded_skills", count=42)
# Returns: "42 beceri yüklendi."

# Get current language
current = get_language()  # "tr"

# Auto-load from config
from core.constants import load_language_from_config
load_language_from_config()
```

### Fallback Chain

If a key is missing in the active language, it falls back to English, then returns the key itself.

### Available Key Categories

- `error_*` — Error messages (35+ keys)
- `success_*` — Success messages
- `info_*` — Informational messages
- `warn_*` — Warning messages
- `confirm_*` — Confirmation prompts
- `label_*` — UI labels
- `prompt_*` — Input prompts
