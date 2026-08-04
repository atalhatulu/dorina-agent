# TASK: İlk-Fonksiyon Otomatik Bağımlılık Kurulumu (kendi kendini iyileştirme)

> Bir tool çağrıldığında `ImportError`/`ModuleNotFoundError` olursa, Dorina hatayı yakalayıp
> eksik paketi belirler ve `uv`/`pip` ile kurar; bir kez sonra devam eder. Kısıtlama değil —
> kendi kendini iyileştirme.
> Tanımlayıcı: `docs/TASKS_AUTO_DEPENDENCY.md`.

## Problem

`tools/builtin/` içindeki bazı tool'lar opsiyonel paketler gerektirir (örn. `psutil`,
`readline`, `yaml`, `httpx2`). Paket kurulu değilse tool `ImportError` ile ölür; kullanıcı
manuel `pip install` yapmak zorunda. `core/error_db.py` zaten bunu logluyor olabilir — ona
dayanarak OTOMATİK kurulum akışı eklenir.

## https://github.com/i/paket

### 1. `tools/dependency_heal.py` (yeni saf/side-effect modül)

```python
def missing_module(exception: Exception) -> str | None:
    """ImportError'dan eksik modül adını regex'le çıkar (ModuleNotFoundError mesajı veya
    varsa exception.name)."""

def pip_name(mod: str) -> str:
    """Modül adı → paket adı map'i. Bilinenler:
       yaml→PyYAML, cv2→opencv-python, PIL→Pillow, psutil→psutil(aynı),
       httpx→httpx, bs4→beautifulsoup4. Bilinmiyorsa ayna modül (çoğu aynı)."""

def install(pkg: str) -> bool:
    """`uv pip install <pkg>` dene; uv yoksa `pip install <pkg>`. Exit 0 ise True.
    Dış komut 60s timeout; hata görmezden gelinir."""
```

### 2. Executor entegrasyonu (`tools/executor.py`)

- Tool handler çalışırken `ImportError`/`ModuleNotFoundError` yakalanırsa:
  1. `missing_module` ile paketi belirle
  2. `pip_name` ile normalize et
  3. `install` ile kur may
  4. Handler'ı BİR kez yeniden dene
  5. İkinci deneme de başarısızsa original hatayı kullanıcıya dön
- Re-entrancy koruması: aynı tool aynı turn içinde 2 kez kurma (loop'a girme).
- Bekleme sırasında (kurulum birkaç saniye) kullanıcıya `⌛ <paket> kuruluyor...` log'u.

### 3. Güvenlik

- Kurulum yalnızca `import X` kaynaklı `ModuleNotFoundError`/`ImportError`'da tetiklenir.
- İnteraktif `?` prompt yok (`--no-input`), onay sormadan kurmaz güvenli paketleri.
- `pip install` asla kullanıcı komut girintisiyle birleşmez; argüman tek paket adı.
- Arka planda değil, senkron; kullanıcı görür.

## Testler (`tests/test_dependency_heal.py`)

1. `missing_module` → `ModuleNotFoundError("No module named 'yaml'")` → `"yaml"`.
2. `pip_name("cv2")` → `"opencv-python"`; `pip_name("yaml")` → `"PyYAML"`; bilinmeyen ayna.
3. `install` gerçek ağ çağrısı YAPMAZ — `monkeypatch` ile `subprocess.run` mock → exit 0 = True.
4. Bilinmeyen modül → `missing_module` None döner (kurmağa çalışmaz).
5. Regresyon: mevcut testler yeşil.

## Kabul (Hermes review)

- [ ] Kurulum yalnızca ImportError tetiğinde; asla kullanıcı komutuyla çalışmaz
- [ ] pip_name map'i doğru; bilinmeyen modül aynısını dener
- [ ] Re-entrancy: aynı tool aynı turn 2 kez kurulmaz
- [ ] mevcut 356 test + yeni testler yeşil

## Kapsam DIŞI

- Mevcut paketleri upgrade etmek (sadece eksik kur)
- Conda/npm/başka package manager desteği başlangıçta yok
- LLM'ye kurulum kararı bırakılmaz (deterministik catch)