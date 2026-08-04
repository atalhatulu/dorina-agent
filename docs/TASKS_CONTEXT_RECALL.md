# TASK: Context Recall — çapraz-session / içerik-tabanlı bağlam hatırlatma

> Yeni session'da, önceki session'ların **mesaj gövdelerinden** ilgili bilgiyi
> bulup, token-bütçeli ve ilgililiksiz-regiontrouble için puanlanmış bir
> "RECALLED CONTEXT" bloğu olarak system prompt'a enjekte eder. Proaktif bağlam
> yönetimi (kısıtlama değil akıllanma).
> Tanımlayıcı: `docs/TASKS_CONTEXT_RECALL.md`.

## Problem (gerçek boşluk)

- `SessionManager.search(query)` (session/manager.py:285) **YALNIZCA** `title` +
  `summary` sütunlarını tarar. Mesaj gövdelerine (`messages` sütunu, Fernet şifreli)
  HİÇ bakmaz. Eski konuşmada bahsedilen bir dosya/karar/komut, özet'e yansımadıysa
  hatırlanamaz.
- Yeni session'da "geçen sefer X'i nasıl yapmıştık?" sorusuna bugün üretken cevap
  yok — agent eski bağlamdan bihaber.

## Hedef

İçerik-tabanlı hatırlatma katmanı: kullanıcı girdisi ilgiliyse, son N session'ın
mesaj gövdelerinden eşleşen snippet'leri bul, puanla, token-bütçeli tek bir bloğa
koyup `_build_system_prompt` akışına ekle. Ses düzeyi: yalnızca sormaya değer
girdilerde, yoksa sessiz.

## Tasarım

### 1. `session/manager.py` — yeni `search_content` metodu

```python
def search_content(self, query: str, limit: int = 5, max_sessions: int = 20) -> list[dict]:
    """Mesaj gövdesi içeriğinde ara. Title/summary yeterli değilse aç."""
```

Davranış:
- Önce hızlı yol: `_index_search(query)` (aşağıda) veya mevcut `.search()` ile aday
  session'ları seç (son 20).
- Her aday için `load(session_id)` (zaten decryption + fallback'li) ile mesajları al.
- Mesaj gövdelerinde `query` kelimeleri (altta: kelime+regex) eşleştir; her mesaj için
  skor (`title` eşleşmesi +2, `summary` +1.5, kullanıcı mesajı +1, asistan +0.5, tool −0.2).
- Eşleşen mesajdan `snippet` (ilk 200 char), `session_id`, `title`, `timestamp` döndür.
- `limit` kadar; token/iş zamanı için `max_sessions` sınırlı. Şifre anahtarı yoksa
  sessiz boş liste (kritik değil, hataya düşme).

### 2. Yeni modül `orchestrator/recall.py`

```python
def should_recall(user_input: str) -> bool:
    """Sorgu hatırlatmaya değer mi? (boş/chat-selam/çok kısa → False). Kullanır:
    len(strip)>6 kelime VE "ne kadar/geçen sefer/daha önce/nasıl yapmıştık/hatırla"
    gibi geçmiş-imleyici kelime VEYA (teknik sözcük: dosya yolu/komut/fonksiyon)."""

def score_relevance(results: list[dict], user_input: str) -> list[dict]:
    """Çıktıyı en ilgiliye göre sırala, puan alt eşiği altını el (EŞİK=2.0).
    Güncel oturumun kendi mesajlarının tekrarını engelle (duplicate guard)."""

def format_recall(results: list[dict], max_chars: int = 1500) -> str:
    """'## RECALLED CONTEXT (prev sessions)' blok şablonu. Aşarsa en düşük puanlıyı at."""
```

Sabitler:
```python
RECALL_MIN_WORDS = 6
RECALL_RELEVANCE_THRESHOLD = 2.0
RECALL_MAX_CHARS = 1500          # config'den gelebilir
RECALL_MAX_SESSIONS = 20
```

### 3. Loop entegrasyonu (`orchestrator/experimental_loop.py`)

- `_build_system_prompt(user_input)` içinde, mevcut bölümlerden sonra:
  ```python
  if settings.recall.enabled and recall.should_recall(user_input):
      res = sm.search_content(user_input, max_sessions=RECALL_MAX_SESSIONS)
      rel = recall.score_relevance(res, user_input)
      block = recall.format_recall(rel)
      if block:
          sections.append(block)   # sistem prompt'una gömülür
  ```
- Config `~/.dorina/config.yaml`: `recall.enabled: bool (default true)`,
  `recall.max_chars: int (1500)`.
- `session_manager`'ı loop içinde zaten varsa kullan (`self`— import etmeyen don't
  duplicate). Semantik memory ile çakışmaz: recall sadece session gövdelerinden,
  semantic farklı depodan.

### 4. `/recall <query>` komutu

- `commands/`'a ek: elle tetikleme, aynı `search_content` + `format_recall` yolunu
  kullanır; çıktıyı doğrudan user'a şifreli session verisi OLARAK değil, düz metin
  özet snippet olarak gösterir (güvenlik: tam mesaj dökme, sadece snippet).

### Koşullar / anti-regresyon

- Tanıtım YOK: `_build_system_prompt` bölüm ekleme mevcut yapıyı bozmaz (append).
- Şifre anahtarı yoksa / db boşsa sessiz boş döner, asla exception fırlatmaz.
- `score_relevance` güncel session'ın kendi içeriğini filtreler (duplicate content
  şikayeti var — bunu önle).
- LLM çağrısı yok; yalnızca regex + skor (deterministik, token-sıfır maliyetli).
- recall çıktısı system prompt'unu her turn şişirmez: `should_recall` kapısı var.

## Testler (`tests/test_recall.py`)

monkeypatch ile `SessionManager.search_content`'ı sabit örnek veriyle mockla:
1. `should_recall("gecen sefer X'i nasil yaptik")` → True; `"merhaba"` / `""` → False.
2. `score_relevance`: ilgili eski session yüksek puan; ilgisiz düşük → eşik altı elenir.
3. `format_recall`: çıktı `RECALLED CONTEXT` içerir; max_chars aşımında en düşük puanlı atılır.
4. Enjeksiyon: sahte `_build_system_prompt` ile recall.blok system prompt'a eklendi.
5. Şifre anahtarı yok / db boş → `search_content` boş liste, patlama yok.
6. Regresyon: mevcut 367 test yeşil.

## Kabul (Hermes review)

- [ ] `search_content` mesaj GÖVDESİNE bakıyor (title/summary değil), şifreli db'de güvenli
- [ ] `should_recall` kapısı çalışıyor (boş/selam turn tetiklemiyor)
- [ ] duplicate-guard güncel session tekrarını engelliyor
- [ ] mevcut 367 + yeni testler yeşil, LLM/ag zv kaçağı yok

## Kapsam DIŞI

- Semantic/episodic memory sisteminin değiştirilmesi (ayrı depo, ayrı iş)
- Full-text engine (SQLite FTS5) eklenmesi — önce basit regex; OPSİYONEL phase 2
- Mevcut `search` metodunun davranışının bozulması (yeni `search_content` eklenir)
- Recall çıktısının prompt'a otomatik TÜM turn eklenmesi (bütçeli, kapılı olmalı)