# TASK: Değer-Tabanlı Context Pruning (Tier 1 yükseltmesi)

> Dorina Agent — `orchestrator/compressor.py`'deki `_compress_fast` (Tier 1)
> kör sıralı silmeyi, turn değer puanlamasına dayalı akıllı budamaya dönüştür.
> Tanımlayıcı: `docs/TASKS_VALUE_PRUNING.md` — Antigravity bu dosyaya göre uygular,
> Hermes review eder.

## Problem

Mevcut `_compress_fast` (compressor.py:137):
- `_split_into_turns` ile turn'leri ayırır
- Sadece son `KEEP_LATEST_TURNS` (4) turn'i tutar
- Gerisine dokunmadan siler → önceki tüm turn'ler deterministik kayıp

Kayıp: turn 5'te kullanıcının ana dosya yolu, verdiği kritik komut, öğrenilen
tercih veya bir hata mesajının anahtarı duruyorsa, turn 8'de sıkışınca hepsi yok olur.

## Hedef

Token tasarrufunu koru (O(1), sıfır LLM çağrısı, Tier 1'de kal) ama silmeyi
"en düşük değerli turn önce" yap. Böylece kritik bilgi TEK bir turn olsa bile
korunur.

## Tasarım

### 1. Yeni modül: `orchestrator/value_scorer.py`

Saf fonksiyonlar, LLM yok, deterministik. API:

```python
def score_turn(turn: list[dict]) -> float:
    """Tek turn'ün bağlam değeri. 0.0 (önemsiz) – 1.0 (kritik)."""

def score_importance(messages: list[dict]) -> float:
    """Tek mesaj için temel önem puanı."""
```

Puanlama kuralları (öncelik sırası):
- `read_file` tool sonucu → **+0.4** (dosya içeriği bağlam için kritik, context.py'de
  zaten `read_file` truncate istisnası var).
- İçerikte `~` veya `/home/` veya bitiş .py/.sh/.md/.rs/.go ile biten tam yol
  regex'i → **+0.35** (dosya yolu).
- Komut/url/ip: `(curl|ssh|git|pip|docker|npm|sudo) ` önekli satır veya
  `https?://` veya IPv4 regex'i → **+0.3**.
- Assistant'ın nihai cevabı (tool_calls olmayan, uzun ≥200 char, karar içeren
  "olacak/karar/yapıldı" fülleri) → **+0.25**.
- Tool sonucu JSON `"error"` içeriyor → **+0.3** (hata bağlamı).
- Kullanıcı mesajı kısa ise (≤80 char) → taban **+0.1** (yeni istek/karar olabilir).
- Assistant tool_calls bloğu + uzun tool çıktıları (read_file değil) → **-0.15**
  (gürültü; ham çıktı yeniden üretilebilir).
- Kısa asistan cevabı (≤60 char) → **-0.05**.

Sonuç `max(0.0, min(1.0, toplam))` ile sınırlanır.

Regex'ler modül sabiti olarak tanımlanır (derlenmiş), test edilir.

### 2. `_compress_fast` yükseltmesi (compressor.py)

Yeni sıra:
1. System turn'lerini daima koru (mevcut davranış).
2. Son `KEEP_LATEST_TURNS` (4) turn'i DAİMA koru (sıcak bağlam — değişmez).
3. Geri kalan eski turn'ler için: token bütçesi aşıldığı için silinecekse,
   `score_turn` ile puanla, **en düşük puanlıdan başlayarak** buda.
4. Token bütçesi fazla değilse: yalnızca `score_importance < ELEME_ESIGI` (0.15)
   olan düşük-değerli turn'leri at; yüksek değerlileri yaşta olsa koru.

Yeni sabitler (modül seviyesi):
```python
ELEME_ESIGI = 0.15   # altında kalan eski turn silinebilir
MAX_TOKENS_OLD = 8000  # eski turn'lerin toplam token üst sınırı (aşılırsa en düşük değerli budanır)
```

Geriye dönük: `should_compress`, `_split_into_turns`, `_compress_llm` (Tier 2),
`estimate_tokens`, `reset` API'leri DEĞİŞMEZ. Yalnızca `_compress_fast` iç gövdesi
değişir; imza aynı kalır.

### 3. Koşullar / anti-regresyon

- System mesajı korunmalı (mevcut davranış korunur).
- `message_count` sonrası asla boş dönülmemeli (her zaman ≥1 turn).
- LLM çağrısı YOK (Tier 1 kalır) — yalnızca regex + sayı.
- Async imza değişmez; `compress()` arayüzü aynı.

## Testler (`tests/orchestrator/`)

`test_value_pruning.py`:
1. Kör silme senaryosu: 8 turn, turn 5'te `/home/teha/proj/main.py` geçen kritik
   user mesajı. Yükseltme sonrası yaşlı ama değerli turn KORUNMALI (blind'de kaybolurdu).
2. Gürültü senaryosu: 8 turn, uzun çıktılı tiw tool'lar → bunlar önce silinir.
3. Deterministiklik: aynı girdi → aynı çıktı (arka arkaya 2 çağrı eşit).
4. System koruması: system turn elemanı her zaman çıktıda.
5. Token sınırı: budama sonrası eski turn token toplamı ≤ MAX_TOKENS_OLD.
6. Yeni testler `pytest tests/orchestrator/test_value_pruning.py -q` geçer,
   mevcut 351 test kırılmaz.

## Kabul kriterleri (Hermes review için)

- [ ] value_scorer.py saf, LLM yok, regex sabitleri derlenmiş
- [ ] _compress_fast değerli yaşlı turn'i koruyor (test 1)
- [ ] gürültü önce budanıyor (test 2)
- [ ] API/imza değişmedi, 351 mevcut test yeşil
- [ ] ~0 tokent LLM çağrısı eklenmedi (Tier 1)
- [ ] ELEME_ESIGI / MAX_TOKENS_OLD tanımlı ve yorumlu

## Kapsam DIŞI (bu task'ta yapma)

- Tier 2 LLM özetleme davranışı değişmez
- context.py/Context sınıfı DEĞİŞMEZ
- /compress, /budget komutları değişmez
- Puanlamaya sinir ağı / LLM eklenmez