"""Narrow all remaining broad except Exception blocks across the project.

Run: python3 _narrow_except.py

This script narrows broad except Exception: blocks to specific exception types
by analyzing the code context around each catch.
"""
import re
import os
import ast
import sys

PROJECT = os.path.dirname(os.path.abspath(__file__))

# Files we've already dealt with (will NOT re-process):
ALREADY_DONE = {
    'browser/client.py',
    'memory/semantic.py',
    'tools/mcp/client.py',
    'search/engine.py',
    'orchestrator/reasoning.py',  # need to check which blocks remain
}


def find_except_exceptions(filepath: str) -> list[dict]:
    """Find all 'except Exception' blocks in a Python file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    relpath = os.path.relpath(filepath, PROJECT)

    lines = content.split('\n')
    result = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Match: except Exception [as e:] or except Exception:
        if stripped.startswith('except ') and 'Exception' in stripped:
            # Check if it's bare 'except Exception' (not a subclass)
            # except Exception: or except Exception as e:
            m = re.match(r'except\s+Exception(\s+as\s+\w+)?\s*:', stripped)
            if m:
                # Get the body (following indented lines)
                # Find indentation of the except line
                indent = len(line) - len(line.lstrip())

                # Find the body
                body_lines = []
                j = i + 1
                while j < len(lines):
                    body_line = lines[j]
                    if body_line.strip() == '':
                        j += 1
                        continue
                    body_indent = len(body_line) - len(body_line.lstrip())
                    if body_indent > indent:
                        body_lines.append(body_line.strip())
                    else:
                        break
                    j += 1

                body = '\n'.join(body_lines)

                result.append({
                    'lineno': i + 1,
                    'text': line,
                    'body': body,
                    'indent': indent,
                    'indent_char': '\t' if '\t' in line[:indent] else ' ',
                })
                # Skip past the body
                # Actually let's just return all and not skip

    return result


def analyze_and_narrow(filepath: str):
    """Analyze the context and suggest what to narrow Exception to."""
    relpath = os.path.relpath(filepath, PROJECT)

    # Read the file
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    lines = content.split('\n')
    modifications = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('except ') and 'Exception' in stripped and 'Exception as' in stripped:
            m = re.match(r'except\s+Exception(\s+as\s+\w+)?\s*:', stripped)
            if not m:
                continue

            lineno = i + 1

            # Get surrounding context (10 lines before)
            context_start = max(0, i - 10)
            context = lines[context_start:i]
            context_str = '\n'.join(context)

            # Get body
            indent = len(line) - len(line.lstrip())
            body_lines = []
            j = i + 1
            while j < len(lines):
                body_line = lines[j]
                if body_line.strip() == '':
                    body_lines.append(lines[j])  # keep blank lines
                    j += 1
                    continue
                body_indent = len(body_line) - len(body_line.lstrip())
                if body_indent > indent:
                    body_lines.append(lines[j])
                else:
                    break
                j += 1

            body_str = '\n'.join(line for line in body_lines if line.strip())

            keywords = context_str.lower() + ' ' + body_str.lower()
            file_ext = os.path.splitext(filepath)[1]

            # Determine the right exception types based on what the code does
            exception_types = set()
            main_types = set()

            # JSON operations
            if any(w in keywords for w in ['json', '.json', 'json.load', 'json.dump', 'jsonify']):
                exception_types.add('json.JSONDecodeError')
                main_types.add('JSON')

            # File operations
            if any(w in keywords for w in ['open(', 'file', 'path', 'read(', 'write(', 'os.', 'shutil', 'pathlib']):
                exception_types.add('OSError')
                main_types.add('file I/O')

            # Subprocess
            if any(w in keywords for w in ['subprocess', 'popen', 'run(', 'call(', 'check_output']):
                exception_types.add('subprocess.CalledProcessError')
                main_types.add('subprocess')

            # HTTP / network
            if any(w in keywords for w in ['request', 'fetch', 'httpx', 'urllib', 'aiohttp', 'http_', 'response', 'status_code']):
                exception_types.add('TimeoutError')
                exception_types.add('OSError')
                main_types.add('HTTP/network')

            # Import
            if any(w in keywords for w in ['import ', 'from ']):
                exception_types.add('ImportError')
                main_types.add('imports')

            # ChromaDB / database
            if any(w in keywords for w in ['chromadb', 'chroma', 'collection', 'embedding']):
                exception_types.add('ValueError')
                exception_types.add('KeyError')
                main_types.add('ChromaDB')

            # Async / asyncio
            if any(w in keywords for w in ['asyncio', 'await', 'stream', 'async ']):
                exception_types.add('asyncio.TimeoutError')
                exception_types.add('OSError')
                main_types.add('async')

            # Dict/key access
            if any(w in keywords for w in ['key', 'index', 'dict', 'get(', "['", "['", 'metadata']):
                exception_types.add('KeyError')
                main_types.add('dict access')

            # Type conversion
            if any(w in keywords for w in ['int(', 'float(', 'str(', 'bool(', 'type(', 'cast', 'convert']):
                exception_types.add('TypeError')
                exception_types.add('ValueError')
                main_types.add('type conversion')

            # Playwright/browser
            if any(w in keywords for w in ['playwright', 'browser', 'page.', 'click(', 'fill(', 'goto(', 'screenshot']):
                exception_types.add('TimeoutError')
                exception_types.add('AttributeError')
                exception_types.add('OSError')
                main_types.add('Playwright/browser')

            # Litellm
            if any(w in keywords for w in ['litellm', 'llm', 'completion', '_summarize']):
                exception_types.add('ImportError')
                exception_types.add('AttributeError')
                exception_types.add('OSError')
                main_types.add('Litellm')

            # Session/export
            if any(w in keywords for w in ['export', 'session', 'token_', 'message']):
                exception_types.add('ImportError')
                exception_types.add('OSError')
                exception_types.add('KeyError')
                main_types.add('session/export')

            # If the body is just logging + pass/continue or returns None/empty/0
            body_clean = body_str.strip()
            purely_internal = (
                any(w in body_clean for w in ['log.', 'logger.', 'print(', 'warn'])
                and not any(w in body_clean for w in ['return ', 'raise '])
            ) if body_clean else True

            # If it's user-facing (returns str(error) or returns error message)
            user_facing = 'return str(' in body_clean or 'return f"' in body_clean and 'error' in body_clean.lower()

            # Decide what to do
            indent_char = '\t' if '\t' in line[:indent] else ' '

            modifications.append({
                'lineno': lineno,
                'old_line': line,
                'exception_types': exception_types,
                'main_types': main_types,
                'purely_internal': purely_internal,
                'user_facing': user_facing,
                'indent': indent,
                'indent_char': indent_char,
                'body_lines': body_lines,
            })

    return modifications


def suggest_replacement(mod: dict) -> str | None:
    """Suggest the replacement line."""
    if not mod['exception_types']:
        return None

    # Sort for consistency
    types = sorted(mod['exception_types'])

    if mod['user_facing']:
        return None  # Don't touch user-facing catches

    new_except = f"except ({', '.join(types)}) as e:"
    return new_except


def process_files():
    """Find all Python files and process them."""
    all_files = []
    for root, dirs, files in os.walk(PROJECT):
        # Skip .git, venv, __pycache__
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'venv', '.venv', 'node_modules', '.claude')]
        for f in files:
            if f.endswith('.py'):
                all_files.append(os.path.join(root, f))

    # Sort for consistent ordering
    all_files.sort()

    total_blocks = 0
    files_with_blocks = []

    for filepath in all_files:
        relpath = os.path.relpath(filepath, PROJECT)

        # Skip already-done files
        if relpath in ALREADY_DONE:
            continue

        mods = analyze_and_narrow(filepath)
        if mods:
            files_with_blocks.append((relpath, mods))
            total_blocks += len(mods)

    print(f"\n=== REMAINING EXCEPT Exception BLOCKS ({total_blocks} total in {len(files_with_blocks)} files) ===\n")

    for relpath, mods in files_with_blocks:
        print(f"\n--- {relpath} ({len(mods)} blocks) ---")
        for m in mods:
            repl = suggest_replacement(m)
            if repl:
                print(f"  L{m['lineno']}: {m['old_line'].strip()}  →  {repl}")
                print(f"       Context: {', '.join(m['main_types']) if m['main_types'] else 'generic'}")
                print(f"       Body: {m['body_lines'][0][:80] if m['body_lines'] else '(empty)'}")
            else:
                print(f"  L{m['lineno']}: {m['old_line'].strip()}  →  [SKIP - user-facing or no types detected]")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Apply mode: python3 _narrow_except.py apply
        if sys.argv[1] == 'apply':
            # Read the output and apply changes
            print("Apply mode not yet implemented in this script")
        else:
            process_files()
    else:
        process_files()
