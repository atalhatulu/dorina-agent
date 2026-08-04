# TASK: Multi-Session Cross-Reference (Bağlam Aktarımı)

> Yeni başlayan bir oturumda, kullanıcının ilk sorgusu geçmiş oturumlardaki 
> önemli verilerle (title ve summary) eşleşiyorsa, geçmişten ilgili
> bağlam otomatik çekilir ve Agent'ın sistem mesajına/ilk turuna eklenir.

## Problem
Kullanıcı yeni bir session açtığında ("dorina chat" veya REPL), Agent önceki 
oturumları tamamen unutur. Örneğin, dün çözülmüş bir DB hatası bugün tekrar 
sorulduğunda Agent sıfırdan düşünür. `memory` kalıcı olsa da, `session` 
bağlamı izoledir.

## Çözüm (Tier 1 - LLM Yok)
Kullanıcının ilk sorgusunu al, `session/cross_reference.py` içerisindeki `extract_keywords`
ile temizle ve filtrele. `sessions.db` içindeki en güncel 100 session'ın 
`title` ve `summary` sütunlarında bu kelimeleri ara. Eşleşme (score) 1'den büyük olan 
en alakalı 2 session'ı bul.

Bulunan session bilgileri (`title`, `date`, `summary`), `orchestrator/experimental_loop.py` 
içindeki `_build_system_prompt` metodunda Sistem Mesajı'na ("### Relevant Past Sessions")
enjekte edilir.

- `session/cross_reference.py`: Bağımsız, deterministik, veritabanı yormayan keyword eşleştiricisi.
- `orchestrator/experimental_loop.py`: `_build_system_prompt` modifikasyonu.
- `tests/session/test_cross_reference.py`: İlgili testler.
