import subprocess
import os

from pathlib import Path
os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parent)

tests = [
    ("1_zero_shot", "Yeni bir React login sayfası uygulaması oluştur. Bana hem index.html hem de app.js dosyasını sıfırdan yaz. Tasarım çok modern olsun."),
    ("2_iteration_budget", "Masaüstünde gizli_dosya.txt adında var olmayan bir dosyayı bul. Eğer okuyamazsan sürekli tekrar dene, asla pes etme."),
    ("4a_memory_save", "Bundan sonra yazacağın tüm web projelerinde CSS framework'ü olarak TailwindCSS kullanmanı istiyorum, bunu tercihlerime kaydet."),
    ("4b_memory_read", "Bana basit bir buton bileşeni yaz."),
    ("5_prologue", "Şu dosyayı oku: test\x00gizli\x0b.txt \ud83d")
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
