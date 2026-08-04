# TASK: Akıllı Query Classification (toolset seçimini akıllandır)

> `tools/toolset.py`'deki `_classify_query` hardcoded keyword listesinden,
> puan tabanlı deterministic bir sınıflandırıcıya yükseltilir.
> Tanımlayıcı: `docs/TASKS_QUERY_CLASSIFY.md`. Sonuç P0'dır: doğru toolset = token tasarrufu,
> kısıtlama değil akıllanma.

## Problem (şu anki `_classify_query`)

- Sırf `in` substring eşleşmesi → yanlış pozitif. Örn `"nasil"` kelimesi `"nasil yapilir kod"`da
  hem read hem code tetikler; sıralama bunu kod'a düşürür ama garantisi yok.
- `"saat"` read kategorisinde ama `"saatlik rapor ureten script yaz"` kod'dur — ayrıştırılamıyor.
- Dil karışık (TR/EN), hiçbir ağırlık yok, niyet (istek vs greeting vs veri çekme) yok.
- `len(text.split()) <= 6` eşiği keyfi; uzun read sorgusu ("2020 istanbul nufusu") read sayılmaz.

## Hedef

Deterministik, puan toplamalı bir sınıflandırıcı. Her sinyal bir puan verir; en yüksek
kategori kazanır. LLM yok. `_classify_query` imzası DEĞİŞMEZ (`(user_input: str) -> str`),
iç gövde ve sabitler değişir.

## Tasarım

### 1. `tools/query_classifier.py` (yeni saf modül)

```python
CATEGORIES = ("read", "chat", "code", "general")

def classify(user_input: str) -> str:
    """Puan tabanlı sınıflandırma."""

def score_greeting(text: str) -> float:
def score_read(text: str) -> float:
def score_code(text: str) -> float:
```

Puan matrisi (sabit, yorumlu):

**Greeting** (öncelik: kısa cümle):
- text sadece selamlaşma kelimelerinden (± noktalama) oluşuyor → +3.0
- kelime sayısı ≤2 ve tool-like karakter yok (`.` `/` `\` `=` `>` `&&`) → +1.5
- Soru işareti yok ve uzunluk <20 char → +0.5

**Read** (bilgi çekme / tek cevap):
- read kavramı: `hava durumu, weather, haber, news, nedir, ne demek, nasil yapilir,
  what is, who is, where, saat kac, fiyat, kac, download, oku, search, fiyat, istatistik,
  nufus, tarih, gundem` → +1.0/kavram
- Şablon: `(ne|kim|nerede|kac|nasil|neden|when|where|who|how|how much)` + (is/are/olduğu)
  → soru fiili → +1.5
- Cümle boyutu küçük (≤10 kelime) ve fiil yok (text, `python`, `api` geçmiyor) → +0.7
- Komut fiili YOKSA (yaz/olustur/calistir/kur/duzelt/build/run/install/fix/create yok) → +0.5

**Code** (dosya/terminal/delegation işi):
- Komut fiili: `yaz, olustur, create, build, compile, calistir, run, kur, install,
  duzelt, fix, hata, debug, test, patch, refactor, fonksiyon, script, class, import,
  dosya, klasor, dizin, python` → +1.0
- Yol/uzantı: regex `\.(py|sh|md|rs|go|js|ts)$` veya `~/` veya sonunda dosya adı → +1.5
- Şablon: `(yaz|olustur|uret|kur|calistir|duzelt) ` + alt + `(kod|script|dosya|fonksiyon)` → +2.0
- `.` `/` `&&` `>` `|` gibi komut karakterleri → +0.8
- Araç çağırma isteği: `grep, liste, tara, say, kac tane, dosyada ara` → +1.0

**Karar**: en yüksek toplam; eşitse `read > code > general > chat` önceliği
(güvenli varsayılan: bilgi isteyeni tool'a boğma). Ama sabitler net olmalı.

### 2. `_classify_query` yükseltmesi (toolset.py)

- İmza değişmez. Gövde `from tools.query_classifier import classify` + sonuç döner.
- `query_toolsets` eşlemesi AYNEN kalır (read→web, chat→{}, code→file+terminal, general→active).
- `tools_enable` her zaman dahil kalır (kısıtlama yok).

### 3. Koşullar / anti-regresyon

- Deterministik: aynı girdi → aynı kategori.
- `get_active_schemas` çağrı mantığı değişmez (yalnızca hangi toolset'lerin geldiği değişir).
- LLM yok, ağ çağrısı yok.
- Bilinen kötü vakalar düzelsin (aşağıdaki testler).

## Testler (`tests/test_query_classifier.py`)

Bu vakalar şu AN Kİ kodda YANLIŞ dönüyor; hepsi assert edilir:
1. `"nasil yapilir istanbul da hava"` → `read` (şu an: code'e düşebiliyor)
2. `"python ile saatlik rapor ureten script yaz"` → `code` (şu an: `saat` read'e çeker)
3. `"merhaba"` → `chat`
4. `"hava durumu"` → `read`
5. `"main.py dosyasinda hata duzelt"` → `code`
6. `""` → `general`; `None`/boş → `general` (patlamaz)
7. `"grep -r todos ~/proj"` → `code`
8. Determinism: aynı girdi 2 kez eşit.

NOT: Bu testler mevcut koda karşı önce çalıştırılıp hangilerinin fail ettiği kaydedilir
(antigravity değişiklikten ÖNCE kırmızı, SONRA yeşil gösterir).

## Kabul kriterleri (Hermes review)

- [ ] query_classifier.py saf, LLM yok, sabit matris yorumlu
- [ ] 8 test + mevcut 356 test yeşil
- [ ] `_classify_query` imza aynı, anti-regresyon yok
- [ ] Temel senaryolarda tool sayısı düşüyor (read sorgusu chat/web dışı tool almıyor)

## Kapsam DIŞI

- Niyet tespitine LLM/ml eklenmesi (deterministik kal)
- tools_enable / get_active_toolsets mantığının değişmesi
- Yeni toolset kategorisi eklenmesi