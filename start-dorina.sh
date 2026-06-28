#!/usr/bin/env bash
# Dorina Agent — Launcher & CLI Installer
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/.venv"
BIN="$HOME/.local/bin"
CMD="$BIN/dorina"

# Auto-create virtualenv if missing
if [ ! -d "$VENV" ]; then
    echo "[setup] Creating virtual environment..."
    python3 -m venv "$VENV"
    echo "[setup] Installing core dependencies..."
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q "$DIR"
fi

# Install/update as global command
mkdir -p "$BIN"
cat > "$CMD" << SCRIPT
#!/usr/bin/env bash
DIR="$DIR"
export PYTHONPATH="\$DIR:\$PYTHONPATH"
exec "\$DIR/.venv/bin/python" "\$DIR/main.py" "\$@"
SCRIPT
chmod +x "$CMD"
echo "[setup] Command updated: $CMD"

# Run
export PYTHONPATH="$DIR:$PYTHONPATH"
exec "$VENV/bin/python" "$DIR/main.py" "$@"
