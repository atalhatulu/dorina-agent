# TASK: Akıllı Tool-Result Belleği (context.py truncation yükseltmesi)

> `orchestrator/context.py`'deki `add_tool_result` tek tip 1500-char kesiyor (badıl read_file).
> Bazı tool sonuçları (web_search/web_fetch özet, terminal grep, json status) kısa ama kritik;
> bazıları (büyük CSV/sayı listesi) context'i çöpe dolduruyor.
> Yükseltme: tool başına akıllı saklama politikası — token tasarrufu, bilgi kaybı değil.
> Tanımlayıcı: `docs/TASKS_TOOL_RESULT_RETENTION.md`.

## Problem

`context.add_tool_result` (context.py:25-59):
- `read_file` hariç her şey 1500 char'a kesiliyor (istediğin: read_file tam kalsın).
- Ama `terminal` çipi hata (kısa, kritik) ile `terminal` büyük çıktı (uzun) aynı muamelede.
- web_search/web_fetch dönen snippet'lerde gömülü karar bilgisi kesik kalabiliyor.
- `count_messages_tokens` ve `estimate_tokens` bu policy'yi bilmiyor.

## Hedef

Tool tipine ve sonucun içeriğine göre 3-sınıflı retention:
- **KEEP_FULL** (tam): `read_file` (mevcut). + Akıllı: sonuç `{"status":"ok"}`-tipi küçük JSON
  ≤800 char ise tam.
- **KEEP_PREVIEW** (özet): `web_search`/`web_fetch`/`terminal` çıktısı kritik sinyal içeriyorsa
  (error/hata, `Traceback`, önemli sayısal değer) daha geniş kes (4000) + ilk+son dilim korunur.
- **TRUNCATE** (kes): uzun tekrarlı/kayıt listesi — 1500 (mevcut) + ortası `...` ve `use X for full`.

## Tasarım

### `orchestrator/context.py` — `add_tool_result`

Mevcut `_MAX_TOOL_RESULT = 1500` yerine, aşağıdaki kurallı küçük bir fonksiyon:

```python
def _decide_result_policy(tool_name: str, result: str) -> tuple[str, int]:
    """(policy, limit). policy: full|preview|truncate"""
```

Politika kararı (deterministik):
- `read_file` → full (sınırsız veya config üst limiti). Mevcut davranış korunur.
- Sonuç JSON parse > başarı (minimal `{"status":"ok"}` veya kayıt sayısı içeren kısa) ve
  `len(result) <= 800` → full.
- `web_search`, `web_fetch`, `knowledge` → preview (limit 4000); içinde error/`hata`/
  `Traceback`/sayısal oran yüksekse önemli dilim ilk+son döner.
- `terminal` → hata içeriyorsa preview(4000), değilse truncate(1500).
- Diğer tool'lar → truncate(1500) (mevcut davranış).
- `name == "read_file"` truncate istisnası AYNEN kalır (davranış bozulmaz).

Yeni modül sabitleri:
```python
TOOL_RESULT_FULL_JSON = 800
TOOL_RESULT_PREVIEW = 4000
TOOL_RESULT_TRUNCATE = 1500  # mevcut
```

### Pipe / yorumlama

Kesilme sonuna mevcut `... (truncated, N bytes total. use <tool> for full)` şablonu korunur.
`full` politikası hiç kesmez (bilgi kaybı yok).

## Testler (`tests/test_context_retention.py`)

1. `read_file` sonucu hiç kesilmez (mevcut korunur).
2. Büyük `web_search` içinde `error` geçiyor → sonuç kesilmiş OLSAYDI BİLE `error` dizesi çıktıda.
3. `terminal` hata dizesi (`Traceback`) içeriyor → `Traceback` çıktıda + limit 4000.
4. `terminal` normal uzun çıktı → 1500 limiti.
5. Kısa JSON `{"status":"ok"}` (≤800) → tam.
6. `count_messages_tokens` davranışı regression yok; yeni test + mevcut 356 test yeşil.

## Kabul (Hermes review)

- [ ] `_decide_result_policy` saf, LLM yok, sabitler yorumlu
- [ ] read_file full korunur; hata sinyali preview'da kaybolmaz
- [ ] mevcut 356 test yeşil, yeni 6 test yeşil
- [ ] truncation şablonu korundu (mesaj sonu yönlendirmesi bozulmadı)

## Kapsam DIŞI

- Kompresyon (compressor.py) değişmez
- Tool'ların kendi dönüş formatı değişmez (sadece context kaydı)
- LLM özetlemesi eklenmez (deterministik string politikası)