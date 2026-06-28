#!/usr/bin/env python3
"""
Wayland'de mouse kontrolü için ydototol wrapper.
PyAutoGUI alternatifi olarak kullanılır.

Kullanım:
    from mouse_wayland import Mouse
    mouse = Mouse()
    mouse.move(500, 300)
    mouse.click()
    mouse.drag(100, 200)
"""

import subprocess
import time
import os
import atexit
import signal


class Mouse:
    """Wayland üzerinde mouse hareketi ve tıklama için ydotool wrapper."""

    def __init__(self, start_daemon: bool = True):
        self._ydotool = self._find_ydotool()
        self._daemon_started = False

        if start_daemon:
            self._ensure_daemon()

        atexit.register(self._cleanup)

    def _find_ydotool(self) -> str:
        """ydotool binary'sini bul."""
        # Önce PATH'te ara
        for path in os.environ.get("PATH", "").split(":"):
            full = os.path.join(path, "ydotool")
            if os.path.isfile(full) and os.access(full, os.X_OK):
                return full
        # which ile dene
        try:
            result = subprocess.run(
                ["which", "ydotool"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        raise RuntimeError("ydotool bulunamadı. Pacman ile yükleyin: sudo pacman -S ydotool")

    def _ensure_daemon(self):
        """ydotoold servisinin çalıştığından emin ol."""
        sock = f"/run/user/{os.getuid()}/.ydotool_socket"
        if os.path.exists(sock):
            return  # Zaten çalışıyor

        # Servisi başlat
        try:
            proc = subprocess.Popen(
                ["ydotoold"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            # Başlaması için bekle
            for _ in range(10):
                if os.path.exists(sock):
                    self._daemon_started = True
                    return
                time.sleep(0.2)

            proc.terminate()
            raise RuntimeError("ydotoold başlatılamadı")
        except FileNotFoundError:
            raise RuntimeError("ydotoold bulunamadı")

    def _cmd(self, *args: str) -> str:
        """ydotool komutunu çalıştır."""
        full_cmd = [self._ydotool] + list(args)
        try:
            result = subprocess.run(
                full_cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                error = result.stderr.strip() or f"exit code {result.returncode}"
                raise RuntimeError(f"ydotool hatası: {error}")
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise RuntimeError("ydotool zaman aşımı")

    def move(self, x: int, y: int):
        """Fareyi mutlak koordinata taşı."""
        self._cmd("mousemove", str(x), str(y))

    def move_relative(self, dx: int, dy: int):
        """Fareyi göreceli olarak hareket ettir."""
        self._cmd("mousemove", "--", str(dx), str(dy))

    def click(self, button: int = 1):
        """
        Tıkla.
        button: 1=Sol, 2=Orta, 3=Sağ
        """
        self._cmd("click", str(button))

    def double_click(self, button: int = 1):
        """Çift tıkla."""
        self.click(button)
        time.sleep(0.05)
        self.click(button)

    def drag(self, x: int, y: int, button: int = 1):
        """Sürükle: mevcut konumdan (x,y)'ye basılı tutarak git."""
        self._cmd("mousedown", str(button))
        self.move(x, y)
        time.sleep(0.05)
        self._cmd("mouseup", str(button))

    def press(self, button: int = 1):
        """Fare düğmesine bas (bırakma)."""
        self._cmd("mousedown", str(button))

    def release(self, button: int = 1):
        """Fare düğmesini bırak."""
        self._cmd("mouseup", str(button))

    def scroll(self, clicks: int = 1):
        """Scroll yap. Pozitif = yukarı, negatif = aşağı."""
        direction = "up" if clicks > 0 else "down"
        self._cmd("scroll", direction, str(abs(clicks)))

    def position(self):
        """Mevcut fare pozisyonunu al (ydotool desteklemiyor, 0,0 döner)."""
        # ydotool pozisyon sorgulamayı desteklemez
        return (0, 0)

    def _cleanup(self):
        """Çıkışta daemon'u temizle."""
        pass  # ydotoold arkada kalsın, sonraki kullanımlar için


# --- Quick test ---
if __name__ == "__main__":
    import sys

    m = Mouse()
    if len(sys.argv) >= 3 and sys.argv[1] == "move":
        m.move(int(sys.argv[2]), int(sys.argv[3]))
        print(f"Mouse moved to ({sys.argv[2]}, {sys.argv[3]})")
    elif len(sys.argv) >= 2 and sys.argv[1] == "click":
        button = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        m.click(button)
        print(f"Mouse clicked button {button}")
    else:
        print("Kullanım: python mouse_wayland.py move X Y")
        print("         python mouse_wayland.py click [1|2|3]")
