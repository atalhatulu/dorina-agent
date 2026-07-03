import subprocess
import os

from pathlib import Path
os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parent)

tests = [
    ("1_zero_shot", "Create a new React login page app. Write both index.html and app.js from scratch. Make the design very modern."),
    ("2_iteration_budget", "Find a non-existent file named hidden_file.txt on the Desktop. If you can't read it, keep trying again, never give up."),
    ("4a_memory_save", "I want you to use TailwindCSS as the CSS framework for all future web projects. Save this to my preferences."),
    ("4b_memory_read", "Write a simple button component."),
    ("5_prologue", "Read this file: test\x00hidden\x0b.txt \ud83d")
]

for name, prompt in tests:
    print(f"Running {name}...")
    with open(f"test_result_{name}.log", "w") as f:
        p = subprocess.Popen(
            ["/home/teha/Documents/GitHub/dorina-agent/.venv/bin/python", "/home/teha/Documents/GitHub/dorina-agent/main.py", "-q", prompt],
            stdin=subprocess.PIPE,
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True
        )
        p.communicate(input="Teha\nDeveloper\ntr\n\n\n")
    print(f"{name} done.")
