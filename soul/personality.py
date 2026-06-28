"""Soul/kişilik motoru - soul.md'yi oku, kişiliği uygula."""

from pathlib import Path
from typing import Optional
import yaml


class Soul:
    """Dorina'nın kişiliği. soul.md'den yüklenir."""

    def __init__(self, path: str | None = None):
        self.path = Path(path) if path else (Path.home() / ".dorina" / "SOUL.md")
        self.raw: dict = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            self.raw = {"name": "dorina", "language": "tr", "KISILIK": [], "DAVRANIS": [], "KURALLAR": [], "TON": []}
            return
        with open(self.path) as f:
            content = f.read()
        # Extract YAML frontmatter (between ---) — only top-level fields
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 2:
                self.raw = yaml.safe_load(parts[1]) or {}
            body = parts[2] if len(parts) >= 3 else ""
        else:
            self.raw = {}
            body = content

        # Also parse markdown sections from body: ## SECTION → list of - items
        # This supports soul.md files written with markdown headings instead of YAML arrays
        if body:
            current_section = None
            for line in body.split("\n"):
                stripped = line.strip()
                if stripped.startswith("## "):
                    current_section = stripped[3:].strip()
                    if current_section not in self.raw:
                        self.raw[current_section] = []
                elif stripped.startswith("- ") and current_section:
                    item = stripped[2:].strip()
                    if item:
                        self.raw.setdefault(current_section, []).append(item)

    @property
    def name(self) -> str:
        return self.raw.get("name", "dorina")

    @property
    def language(self) -> str:
        return self.raw.get("language", "tr")

    @property
    def personality_lines(self) -> list[str]:
        """Kişilik maddelerini döndür (Türkçe ve İngilizce bölüm adlarını destekler)."""
        result = []
        # Map to normalized names, deduplicate
        section_map = {
            "KISILIK": "KISILIK", "PERSONALITY": "KISILIK",
            "DAVRANIS": "DAVRANIS", "BEHAVIOR": "DAVRANIS", "BEHAVIOUR": "DAVRANIS",
            "KURALLAR": "KURALLAR", "RULES": "KURALLAR",
            "TON": "TON", "TONE": "TON",
        }
        seen = set()
        for raw_section, norm_section in section_map.items():
            if norm_section in seen:
                continue
            items = self.raw.get(raw_section, [])
            if items:
                seen.add(norm_section)
                result.append(f"\n## {norm_section}")
                result.extend(f"- {item}" for item in items)
        return result

    @property
    def system_prompt(self) -> str:
        """Soul'dan system prompt oluştur."""
        lines = [
            f"Adın {self.name}. Aşağıdaki kurallara uy.",
        ]
        lines.extend(self.personality_lines)
        # Kullanici profili varsa ekle
        _profile_path = Path.home() / ".dorina" / "user_profile.json"
        if _profile_path.exists():
            try:
                import json as _json
                _profile = _json.loads(_profile_path.read_text())
                lines.append("")
                lines.append("## KULLANICI PROFILI")
                lines.append(f"- Adi: {_profile.get('name', '?')}")
                lines.append(f"- Meslek: {_profile.get('profession', '?')}")
                if _profile.get('age'):
                    lines.append(f"- Yas: {_profile['age']}")
                if _profile.get('os'):
                    lines.append(f"- Isletim sistemi: {_profile['os']}")
                lines.append(f"- Ana dizin: {_profile.get('project_dir', str(Path.cwd()))}")
                if _profile.get('editor'):
                    lines.append(f"- Editor: {_profile['editor']}")
                # Kisiselik stili system prompt'un tonunu belirler
                _style = _profile.get('personality_style', 'dengeli')
                if _style == 'professional':
                    lines.append("")
                    lines.append("## TON")
                    lines.append("- Kisa, oz, teknik cevaplar ver.")
                    lines.append("- Gereksiz yorum yapma, sadece isi yap.")
                    lines.append("- Emoji kullanma.")
                elif _style == 'arkadas':
                    lines.append("")
                    lines.append("## TON")
                    lines.append("- Samimi, sicak ve arkadas canlisi ol.")
                    lines.append("- Ara sira espri yap, emoji kullan.")
                    lines.append("- Kullaniciya ismiyle hitap et.")
                # dengeli: varsayilan, ekstra kural gerekmez
            except Exception:
                pass
                
        # Kalici Hafiza (HERMES TARZI: ~/.dorina/memories/ altinda)
        _mem_user = Path.home() / ".dorina" / "memories" / "USER.md"
        _mem_memory = Path.home() / ".dorina" / "memories" / "MEMORY.md"
        _mem_skill_dir = Path.home() / ".dorina" / "skills"
        _mem_found = []
        if _mem_user.exists():
            _mem_found.append(("KULLANICI PROFILI", _mem_user.read_text(encoding="utf-8").strip()))
        if _mem_memory.exists():
            _mem_found.append(("AGENT NOTLARI", _mem_memory.read_text(encoding="utf-8").strip()))
        if _mem_skill_dir.exists():
            _skill_entries = []
            for _skill_folder in sorted(_mem_skill_dir.iterdir()):
                if _skill_folder.is_dir():
                    _sk = _skill_folder / "SKILL.md"
                    if _sk.exists():
                        _content = _sk.read_text(encoding="utf-8").strip()
                        _skill_entries.append(f"[{_skill_folder.name}]")
                        _skill_entries.append(_content)
            if _skill_entries:
                _mem_found.append(("OGRENILEN BECERILER", "\n".join(_skill_entries)))
        for title, content in _mem_found:
            lines.append("")
            lines.append(f"## {title}")
            # Sadece ilk 10 satir enjekte et, fazlasi icin read_memory kullan
            _mem_lines = content.split("\n")
            for line in _mem_lines[:10]:
                lines.append(line)
            if len(_mem_lines) > 10:
                lines.append(f"  *(+{len(_mem_lines)-10} satir daha — read_memory ile oku)*")

        # Prosedürel Hafıza (Kullanıcı Tercihleri)
        _pref_path = Path.home() / ".dorina" / "knowledge" / "learned" / "preferences.json"
        if _pref_path.exists():
            try:
                import json as _json
                _prefs = _json.loads(_pref_path.read_text())
                if _prefs:
                    lines.append("")
                    lines.append("## KULLANICI TERCİHLERİ (PROSEDÜREL HAFIZA)")
                    for k, v in _prefs.items():
                        lines.append(f"- {k}: {v}")
            except Exception:
                pass
                
        # Always append tool usage instructions
        lines.append("")
        lines.append("## TOOL KULLANIMI")
        lines.append("- Sorulara cevap vermek icin tool'lari KULLAN. Konusarak degil, tool cagirarak yap.")
        lines.append("- 'Su dosyayi okuyayim' deme → read_file cagir.")
        lines.append("- 'Su komutu calistirayim' deme → terminal cagir.")
        lines.append("- 'Simdi sunu yazayim' deme → write_file cagir.")
        lines.append("- Eger tool cagirmiyorsan, YA final cevabi veriyor ol YA da is bitmistir.")
        lines.append("- Plan yapma, yapacagini anlatma. Dogrudan uygula.")
        lines.append("- Bir tool hata verirse pes etme. Once web'de arastir (web_search), cozumu bul, terminal ile kur, sonra tekrar dene.")
        lines.append("- Asla 'yapamam' deme. Once cozum ara, sonra konus.")
        lines.append("")
        lines.append("## GOREV TAMAMLAMA")
        lines.append("- Cok adimli bir gorev aldiginda onay bekleme, direkt basla ve tamamla.")
        lines.append("- 'Once su sekilde baslayayim' deyip durma — basla VE devam et.")
        lines.append("- Sadece su durumlarda onay iste: dosya silme, sistem genelinde degisiklik, geri alinamaz islem.")
        lines.append("- Plan yaptiysan uygula. 'Simdi X yapayim' dedikten sonra X'i yap, input bekleme.")
        lines.append("- **En iyi kod yazmadigindir (Ponytail).** Gereksiz paket/paket kurma. Browser'in hazir elementini kullan (`<input type='date'>` flatpickr yerine). Tek satirda coz. YAGNI: ihtiyacin olmayani ekleme.")
        lines.append("- Gorev bitmeden DONE'a gecme.")
        lines.append("- **Gorev bittiginde ogrendigin kalibi save_memory ile kaydet.** Ornek: HTML oyun sitesi yaptiysan → `save_memory(target='skill', content='html-website: canvas + requestAnimationFrame + CSS grid')`. Spesifik degil, GENEL ve TEKRAR KULLANILABILIR olsun.")
        lines.append("- **Arastirma yaptiysan ogrendiklerini kaydet.** web_search veya deep_research ile bir konuda bilgi topladiysan, cikardigin ozeti save_memory(target='skill') ile kaydet. Boylece bir daha ayni seyi arastirmazsin.")
        lines.append("")
        lines.append("## CONTEXT KULLANIMI")
        lines.append("- Bir dosyayi bir kere okudugunda, icerigi konusma gecmisinde var demektir.")
        lines.append("- AYNI dosyayi TEKRAR okumana gerek yok. Konusma gecmisindeki bilgiyi kullan.")
        lines.append("- Sadece dosya degismis olabileceginden supheleniyorsan tekrar oku.")
        lines.append("- Ihtiyacin olan bilgiyi once konusma gecmisinde ara.")
        lines.append("")
        lines.append("## TOKEN TASARRUFU")
        lines.append("- write_file ile dosya yazdiktan sonra icerigi asistan mesajinda TEKRARLAMA. Sadece 'dosya olusturuldu' de.")
        lines.append("- read_file ile okudugunda dosyanin TAMAMINI cevabinda gosterme. Ozet gec veya sadece ilgili kisimlari belirt.")
        lines.append("- Tool call argumanlarinda buyuk icerikler gonderirsen cok token harcanir. Terminal ile python -c kullan.")
        lines.append("- **Toplu taramalarda batch_python tool'unu kullan.** 20+ dosya tarayacaksan read_file ile tek tek okuma. batch_python ile tek script'te tumunu tara.")
        lines.append("- **Kalici hafiza:** Kullaniciyla ilgili kisisel bilgi (yas, isim, tercih) → target='user'. Kendi notlarin (tool, ortam) → target='memory'. Ogrendigin teknik kalip → target='skill'.")
        lines.append("")
        lines.append("## PATCH SONRASI KURAL")
        lines.append("- patch basarili dondurduyse verification alaninda degisen satirlar ve cevresi gelir.")
        lines.append("- dosyayi TEKRAR okuma. Verification bolumu degisikligi dogrular.")
        lines.append("- read_file → patch → read_file dizisi YASAKTIR.")
        lines.append("- Birden fazla yeri değiştireceksen BATCH PATCH (changes argümanı) kullan. Tek dosyada arka arkaya patch çağırma.")
        lines.append("")
        lines.append("## DOGRULUK")
        lines.append("- Her tool sonucu [tool_adi] → ... formatinda gelir. Bu bir provenans etiketidir.")
        lines.append("- Tool'dan gelen bilgi her zaman dogrudur. Tool'a guven, kendin bilgi uydurma.")
        lines.append("- Bir sayi, dosya adi veya deger vermen gerekiyorsa: once tool'a sor, sonucu kullan.")
        lines.append("- Tool sonucunda olmayan hicbir bilgiyi 'kesin' olarak sunma. 'Tahminen', 'gorunuse gore' gibi ifadeler kullan.")
        lines.append("")
        lines.append("## HATA YONETIMI")
        lines.append("- Tool hata verdiginde: sebebini acikla (Permission denied, not found, timeout).")
        lines.append("- Basarisiz adimlari ✗ ile, basarili adimlari ✓ ile isaretle.")
        lines.append("- Hata sonrasi alternatif yontem dene. Alternatif yoksa kullaniciya bildir.")
        lines.append("- 'Cozum araniyor...' gibi bos mesajlar gosterme. Dogrudan alternatife gec veya raporla.")
        return "\n".join(lines)

    def reload(self):
        """soul.md değiştiyse yeniden yükle."""
        self._load()


soul = Soul()
