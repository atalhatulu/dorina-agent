"""Find and analyze all 'except Exception' blocks across the project."""
import os
import re
import json

PROJECT = '/home/teha/Documents/GitHub/dorina-agent'

# Files already done (don't re-check)
ALREADY_DONE = {
    'browser/client.py',
    'memory/semantic.py',
    'tools/mcp/client.py',
    'search/engine.py',
}

SKIP_DIRS = {'__pycache__', '.git', 'venv', '.venv', 'node_modules', '.claude'}

results = {}
internal = []
user_facing = []
already_narrowed = []

for root, dirs, files in os.walk(PROJECT):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if not f.endswith('.py'):
            continue
        fpath = os.path.join(root, f)
        relpath = os.path.relpath(fpath, PROJECT)

        if relpath in ALREADY_DONE:
            continue

        with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
            lines = fh.readlines()

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Match: except Exception, except Exception as X:
            m = re.match(r'except\s+Exception(\s+as\s+\w+)?\s*:', stripped)
            if not m:
                continue

            lineno = i + 1

            # Get body
            indent = len(line) - len(line.lstrip())
            body_lines = []
            j = i + 1
            while j < len(lines):
                bl = lines[j]
                if bl.strip() == '':
                    j += 1
                    continue
                bindent = len(bl) - len(bl.lstrip())
                if bindent > indent:
                    body_lines.append(bl.strip())
                else:
                    break
                j += 1

            body = '; '.join(body_lines)

            # Check if user-facing (returns str/error)
            is_user_facing = False
            for bl in body_lines:
                if bl.startswith('return ') and ('str(' in bl or 'f"' in bl or '"' in bl):
                    is_user_facing = True
                    break
                if 'return "' in bl or "return '" in bl:
                    is_user_facing = True
                    break

            # Check if already narrowed
            is_narrowed = False
            if not stripped.startswith('except Exception'):
                # Already has specific exceptions
                is_narrowed = True
                continue

            entry = {
                'lineno': lineno,
                'text': stripped,
                'body': body[:120],
                'user_facing': is_user_facing,
            }

            if is_user_facing:
                user_facing.append((relpath, entry))
            else:
                internal.append((relpath, entry))

# Output as JSON for machine reading
output = {
    'internal': [(f, e) for f, e in internal],
    'user_facing': [(f, e) for f, e in user_facing],
}

with open('/tmp/narrow_results.json', 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

# Also print summary
print(f"=== INTERNAL (should narrow): {len(internal)} blocks ===")
for fpath, entry in sorted(internal):
    print(f"\n{fpath}:L{entry['lineno']}")
    print(f"  except: {entry['text']}")
    print(f"  body: {entry['body']}")

print(f"\n\n=== USER-FACING (skip): {len(user_facing)} blocks ===")
for fpath, entry in sorted(user_facing):
    print(f"  {fpath}:L{entry['lineno']} — {entry['body'][:80]}")
