#!/usr/bin/env python3
"""
Kendi kendini restart eden script.
Maksimum restart sayısı ile kontrollü çalışır.
"""

import os
import sys
import time

# Restart sayacı dosyası
COUNTER_FILE = "/tmp/self_restart_counter.txt"
MAX_RESTARTS = 5

def get_counter():
    try:
        with open(COUNTER_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0

def set_counter(val):
    with open(COUNTER_FILE, "w") as f:
        f.write(str(val))

def main():
    counter = get_counter()
    counter += 1
    set_counter(counter)

    print(f"{'='*50}")
    print(f"🔄 Self-Restart Script v1.0")
    print(f"📊 Restart sayısı: {counter}/{MAX_RESTARTS}")
    print(f"🐍 Python: {sys.version.split()[0]}")
    print(f"📂 Çalışma dizini: {os.getcwd()}")
    print(f"🆔 PID: {os.getpid()}")
    print(f"{'='*50}")

    if counter >= MAX_RESTARTS:
        print(f"\n✅ Maksimum restart sayısına ulaşıldı ({MAX_RESTARTS}). Script sonlanıyor.")
        print("🧹 Temizlik yapılıyor...")
        os.remove(COUNTER_FILE)
        sys.exit(0)

    print(f"\n⏳ 3 saniye içinde yeniden başlıyorum...")
    time.sleep(3)

    print(f"♻️ Restart #{counter} başlatılıyor...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

if __name__ == "__main__":
    main()
