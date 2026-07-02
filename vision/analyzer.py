"""Görsel analiz — resim oku, OCR yap, yeniden boyutlandır, format değiştir, thumbnail oluştur."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from core.logger import log


class VisionAnalyzer:
    def __init__(self):
        self.available = False
        self._check_deps()

    def _check_deps(self):
        try:
            from PIL import Image
            self.available = True
        except ImportError:
            self.available = False

    # ── Analyze ─────────────────────────────────────────────────
    def analyze(self, image_path: str) -> str:
        """Resim dosyasını analiz et: format, boyut, mod, dosya bilgisi."""
        if not self.available:
            return "Vision kullanilamiyor (Pillow kurulu degil)"
        try:
            from PIL import Image
            p = Path(image_path)
            if not p.exists():
                return f"Dosya bulunamadi: {image_path}"
            with Image.open(p) as img:
                info = {
                    "format": img.format or "bilinmiyor",
                "size": f"{img.size[0]}x{img.size[1]}",
                "mode": img.mode,
                "file": str(p),
                "file_size": f"{p.stat().st_size} bytes",
            }
            return (
                f"Resim: {info['size']} {info['format']} {info['mode']} "
                f"({info['file_size']})"
            )
        except Exception as e:
            return f"Resim analiz edilemedi: {e}"

    def analyze_detailed(self, image_path: str) -> dict:
        """Detaylı analiz sonucu sözlük olarak döndür."""
        if not self.available:
            return {"error": "Vision kullanilamiyor", "available": False}
        try:
            from PIL import Image
            p = Path(image_path)
            if not p.exists():
                return {"error": f"Dosya bulunamadi: {image_path}"}
            with Image.open(p) as img:
                return {
                    "format": img.format or "unknown",
                    "width": img.size[0],
                    "height": img.size[1],
                "mode": img.mode,
                "file": str(p),
                "file_size": p.stat().st_size,
                "available": True,
            }
        except Exception as e:
            return {"error": str(e), "available": False}

    # ── OCR ─────────────────────────────────────────────────────
    def ocr(self, image_path: str) -> str:
        """Optik Karakter Tanıma (easyocr gerekli).
        easyocr yoksa yerine PIL+debug mesajı döndürür.
        """
        if not self.available:
            return "Vision kullanilamiyor"
        try:
            import easyocr
            reader = easyocr.Reader(["en", "tr"], gpu=False)
            result = reader.readtext(image_path, detail=0)
            text = "\n".join(result) if result else "Metin bulunamadi"
            return f"[OCR] {len(result)} parca:\n{text}"
        except ImportError:
            return f"[OCR: {image_path} - easyocr gerekli]"
        except Exception as e:
            return f"[OCR] Hata: {e}"

    # ── Resize ──────────────────────────────────────────────────
    def resize(self, image_path: str, width: int = 800, height: int = 0, keep_aspect: bool = True) -> str:
        """Resmi yeniden boyutlandır.
        - width: hedef genişlik (piksel)
        - height: 0 ise en-boy oranı korunarak hesaplanır
        - keep_aspect: True ise oran korunur, False ise tam width×height
        """
        if not self.available:
            return "Vision kullanilamiyor"
        try:
            from PIL import Image
            p = Path(image_path)
            if not p.exists():
                return f"Dosya bulunamadi: {image_path}"

            with Image.open(p) as img:
                orig_w, orig_h = img.size

                if height > 0 and not keep_aspect:
                    new_size = (width, height)
                elif height > 0 and keep_aspect:
                    ratio = min(width / orig_w, height / orig_h)
                    new_size = (int(orig_w * ratio), int(orig_h * ratio))
                else:
                    ratio = width / orig_w
                    new_size = (width, int(orig_h * ratio))

                img = img.resize(new_size, Image.LANCZOS)

                stem = p.stem
                suffix = p.suffix or ".png"
                out_path = p.parent / f"{stem}_{new_size[0]}x{new_size[1]}{suffix}"
                img.save(out_path)
            return (
                f"Yeniden boyutlandirildi: {out_path.name} "
                f"({orig_w}x{orig_h} -> {new_size[0]}x{new_size[1]})"
            )
        except Exception as e:
            return f"Yeniden boyutlandirilamadi: {e}"

    # ── Format Conversion ──────────────────────────────────────
    def convert_format(self, image_path: str, target_format: str = "png", output_path: Optional[str] = None) -> str:
        """Resim formatını dönüştür.
        Desteklenen formatlar: PNG, JPEG, BMP, GIF, WEBP, TIFF.
        """
        if not self.available:
            return "Vision kullanilamiyor"
        valid_formats = {"png", "jpeg", "jpg", "bmp", "gif", "webp", "tiff", "tif"}
        target = target_format.lower()
        if target == "jpg":
            target = "jpeg"
        if target not in valid_formats:
            return (
                f"Gecersiz format: {target_format}. "
                f"Secenekler: {', '.join(sorted(valid_formats))}"
            )

        try:
            from PIL import Image
            p = Path(image_path)
            if not p.exists():
                return f"Dosya bulunamadi: {image_path}"

            with Image.open(p) as img:
                # RGBA -> RGB (JPEG desteklemez)
                if target in ("jpeg", "jpg") and img.mode == "RGBA":
                    img = img.convert("RGB")

                if output_path:
                    out = Path(output_path)
                else:
                    out = p.parent / f"{p.stem}.{target}"

                out.parent.mkdir(parents=True, exist_ok=True)
                save_kwargs = {}
                if target == "jpeg":
                    save_kwargs["quality"] = 90
                elif target == "png":
                    save_kwargs["optimize"] = True

                img.save(str(out), format=target.upper(), **save_kwargs)
            return f"Format degistirildi: {p.name} -> {out.name} ({target.upper()})"
        except Exception as e:
            return f"Format degistirilemedi: {e}"

    # ── Thumbnail ──────────────────────────────────────────────
    def thumbnail(self, image_path: str, size: tuple[int, int] = (200, 200), output_path: Optional[str] = None) -> str:
        """Küçük resim (thumbnail) oluştur. En-boy oranını korur, boyutları aşmaz."""
        if not self.available:
            return "Vision kullanilamiyor"
        try:
            from PIL import Image
            p = Path(image_path)
            if not p.exists():
                return f"Dosya bulunamadi: {image_path}"

            with Image.open(p) as img:
                img.thumbnail(size, Image.LANCZOS)

                if output_path:
                    out = Path(output_path)
                else:
                    out = p.parent / f"{p.stem}_thumb{size[0]}x{size[1]}{p.suffix or '.png'}"

                out.parent.mkdir(parents=True, exist_ok=True)
                img.save(out)
                return (
                    f"Thumbnail olusturuldu: {out.name} "
                    f"({size[0]}x{size[1]} - gercek: {img.size[0]}x{img.size[1]})"
                )
        except Exception as e:
            return f"Thumbnail olusturulamadi: {e}"

    # ── Utility ─────────────────────────────────────────────────
    def get_image_info(self, image_path: str) -> Optional[dict]:
        """Resim hakkında temel bilgileri sözlük olarak döndür.
        Hata durumunda None döndürür.
        """
        if not self.available:
            return None
        try:
            from PIL import Image
            p = Path(image_path)
            if not p.exists():
                return None
            with Image.open(p) as img:
                return {
                    "format": img.format,
                    "width": img.size[0],
                    "height": img.size[1],
                    "mode": img.mode,
                    "file_size": p.stat().st_size,
                    "path": str(p),
                }
        except (OSError, AttributeError, ValueError, ImportError):
            return None


vision = VisionAnalyzer()
