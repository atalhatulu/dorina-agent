# FUTURE.md — Dorina Agent Gelecek Planları

> Bu dosya README'de referans verilen tasarım disiplinidir: **"ileride lazım
> olur" diye koda kod eklenmez**, buraya yazılır, gerektiğinde oradan alınır.
> Fikirler burada bekler; yalnızca net bir değer doğrulandığında koda taşınır.

## Adaylar (öncelik yok — hepsi fikir)

- **Bellman-Ford / transformcisi context pruning** — token bütçesi aşıldığında
  en düşük değerli mesajları akıllıca budama (mevcut sıralı silmenin yerine).
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

## Taşıma kuralı

Bir fikir koda alınacaksa:
1. Önce tespit: neden şimdi, hangi kullanıcı problemini çözüyor?
2. Eski ve az kullanılan bir şeyi sil (20K-25K bandı disiplini).
3. Test yaz, sonra uygula.