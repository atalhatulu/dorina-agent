# FUTURE.md — Dorina Agent Gelecek Planları

> Bu dosya README'de referans verilen tasarım disiplinidir: **"ileride lazım
> olur" diye koda kod eklenmez**, buraya yazılır, gerektiğinde oradan alınır.
> Fikirler burada bekler; yalnızca net bir değer doğrulandığında koda taşınır.

## Adaylar (öncelik yok — hepsi fikir)

- **~~Bellman-Ford / transformcisi context pruning~~** — ✅ KODDA: value-based pruning
  (`orchestrator/value_scorer.py` + Tier 1 `_compress_fast`), turn değer puanlamasıyla
  `docs/TASKS_VALUE_PRUNING.md`.
- **Multi-session cross-referans** — eski session'dan ilgili bilgiyi otomatik
  çekip bağlam bilinciyle kullanma.
- **Plugin sistemi** — üçüncü taraf tool/provider paketi yükleme.
- **Self-hosted model önceliği** — Ollama sağlık kontrolü varsa yerel modele
  geç, maliyet düşür.
- **Dashboard'a canlı tool adımı görselleştirmesi** — WebSocket üzerinden
  adım-adım aksiyon izleme (kısmen mevcut, derinleştirilebilir).
- **İnsan onayındaki konuşma maliyeti** — approval beklerken harcanan turları
  kompres etme.
- **Arayüz temaları** — kullanıcı tanımlı renk paleti.
- **Otomatik regression benchmark** — her PR'da kritik akışların (başlatma,
  /setup, tool seçimi) hız testi.

### Para Kazanma (Monetization) & Otonom Hedefler
- **Bug Bounty Otomasyonu & Otonom Sızma Testi** — Açık kaynak projeleri veya yasal hedefleri (ör: OWASP Juice Shop) tarayarak zafiyet (XSS, SQLi, IDOR) bulma ve PoC (Proof of Concept) üretme.
- **Playwright (Browser Otomasyonu) Aracı** — SPA'lar (Single Page Applications) üzerinde çalışabilmek, DOM manipülasyonu, form doldurma ve intercept üzerinden gizli API endpointlerini yakalamak için. (Bug Bounty'nin temel şartı).
- **GitHub App / SaaS Entegrasyonu** — Dorina'nın dış webhook'ları dinleyerek açılan PR'larda Code Review, güvenlik denetimi veya otonom bug-fix atmasını sağlamak.
- **Otonom Freelancer Modu** — Upwork / GitHub Bounties gibi platformlarda issue bulup kendi kendine klonla-çöz-PR at döngüsünü işletmesi.

## Taşıma kuralı

Bir fikir koda alınacaksa:
1. Önce tespit: neden şimdi, hangi kullanıcı problemini çözüyor?
2. Eski ve az kullanılan bir şeyi sil (20K-25K bandı disiplini).
3. Test yaz, sonra uygula.