#!/usr/bin/env python3
"""
Self-restarting script.
Runs with a maximum restart counter for controlled execution.
"""

import os
import sys
import time

# Restart counter file
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
    print(f"📊 Restart count: {counter}/{MAX_RESTARTS}")
    print(f"🐍 Python: {sys.version.split()[0]}")
    print(f"📂 Working directory: {os.getcwd()}")
    print(f"🆔 PID: {os.getpid()}")
    print(f"{'='*50}")

    if counter >= MAX_RESTARTS:
        print(f"\n✅ Maximum restart count reached ({MAX_RESTARTS}). Script terminating.")
        print("🧹 Cleaning up...")
        os.remove(COUNTER_FILE)
        sys.exit(0)

    print(f"\n⏳ Restarting in 3 seconds...")
    time.sleep(3)

    print(f"♻️ Starting restart #{counter}...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

if __name__ == "__main__":
    main()
