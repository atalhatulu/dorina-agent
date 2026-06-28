#!/usr/bin/env bash
set -euo pipefail

# Dorina Agent — tek komut kurulum
# Usage: curl -fsSL https://raw.githubusercontent.com/atalhatulu/dorina-agent/main/scripts/install.sh | bash

REPO="https://github.com/atalhatulu/dorina-agent"
INSTALL_DIR="${DORINA_DIR:-$HOME/.dorina}"
BIN_DIR="$HOME/.local/bin"
PYTHON="${PYTHON:-python3}"

echo "==> Dorina Agent kuruluyor..."

# 1. Python kontrol
if ! command -v "$PYTHON" &>/dev/null; then
    echo "HATA: Python bulunamadi. Python >=3.10 kurun."
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  macOS: brew install python@3.11"
    echo "  Arch: sudo pacman -S python python-pip"
    exit 1
fi

PY_VER=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ $(echo "$PY_VER < 3.10" | bc -l 2>/dev/null || echo 1) -eq 1 ]]; then
    echo "HATA: Python 3.10+ gerekli, mevcut: $PY_VER"
    exit 1
fi
echo "  Python $PY_VER ✓"

# 2. Git kontrol (clone icin)
if ! command -v git &>/dev/null; then
    echo "HATA: git bulunamadi."
    echo "  Ubuntu/Debian: sudo apt install git"
    echo "  macOS: brew install git"
    echo "  Arch: sudo pacman -S git"
    exit 1
fi

# 3. Projeyi clone la
TMP_DIR=$(mktemp -d)
echo "==> Proje indiriliyor..."
git clone --depth 1 "$REPO" "$TMP_DIR" 2>/dev/null || {
    echo "HATA: Proje indirilemedi: $REPO"
    rm -rf "$TMP_DIR"
    exit 1
}

# 4. Sanal ortam olustur
echo "==> Sanal ortam hazirlaniyor..."
"$PYTHON" -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"
pip install --quiet --upgrade pip 2>/dev/null
pip install --quiet "$TMP_DIR" 2>/dev/null || pip install --quiet -r "$TMP_DIR/requirements.txt" 2>/dev/null

# 5. Config olustur
if [[ ! -f "$INSTALL_DIR/config.yaml" ]]; then
    cp "$TMP_DIR/config.yaml.example" "$INSTALL_DIR/config.yaml"
    echo "  Config: $INSTALL_DIR/config.yaml"
fi

# 6. PATH'e ekle
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/dorina" << 'SCRIPT'
#!/usr/bin/env bash
DORINA_DIR="${DORINA_DIR:-$HOME/.dorina}"
exec "$DORINA_DIR/venv/bin/python" -m main "$@"
SCRIPT
chmod +x "$BIN_DIR/dorina"

# PATH'e eklendi mi kontrol
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    SHELL_CONFIG="$HOME/.bashrc"
    if [[ "$SHELL" == *"zsh"* ]]; then
        SHELL_CONFIG="$HOME/.zshrc"
    fi
    echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$SHELL_CONFIG"
    echo "  PATH eklendi: $BIN_DIR → $SHELL_CONFIG"
    echo "  Terminali yeniden baslat veya 'source $SHELL_CONFIG' yap."
fi

# 7. Temizlik
rm -rf "$TMP_DIR"

echo ""
echo "==> Dorina Agent kuruldu! 🚀"
echo ""
echo "  Kullanmak icin: dorina"
echo "  API key eklemek icin: $INSTALL_DIR/keys.json"
echo "  Config: $INSTALL_DIR/config.yaml"
echo ""
echo "  Ilk calistirmada profil wizardi acilir."
