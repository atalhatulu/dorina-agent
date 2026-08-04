# TASK: A2A Server — Dorina'yı Agent2Agent endpoint yap

> Dorina'nın mevcut FastAPI gateway'i (localhost:5792) üzerine Google **A2A
> (Agent2Agent, spec 2025-03/2025-04)** arayüzü eklenir. Diğer A2A agent'lar /
> sistemler Dorina'ya network üzerinden task atıp yanıt alabilir. Zaten var olan
> `loop_v2.process(query)` ve builder `verify_token` kullanılacak.
> Tanımlayıcı: `docs/TASKS_A2A_SERVER.md`. UYGULAYAN: antigravity. REVIEW: Hermes.

## Kapsam / amaç

- Dorina tek bir agent olarak A2A üzerinden service edilir.
- REST örülü JSON-RPC 2.0 (ek harici SDK bağımlılığı YOK — elle minimal uygulama).
- Uzaktan sorgu → `loop_v2.process(query)` → `completed` task + `artifacts` içinde yanıt.

## KONUM / dosyalar

1. `gateway/a2a.py` (yeni) — A2A yönlendirme mantığı + AgentCard.
2. `gateway/app.py` — `app.include_router` veya endpoint ekleme (aşağıda tam ara yüz).
3. `tests/gateway/test_a2a.py` (yeni).

## Endpoint'l] (A2A 2025-03 konsol tasarımı)

**1) AgentCard — `GET /.well-known/agent.json`**
```json
{
  "name": "Dorina",
  "description": "CLI AI agent endpoint",
  "url": "http://127.0.0.1:5792/a2a",
  "provider": {"organization": "atalhatulu"},
  "version": "0.1.0",
  "capabilities": {"streaming": false, "pushNotifications": false},
  "skills": [{"id": "dorina-chat", "name": "General chat & code", "description": "Run Dorina"}]
}
```

**2) JSON-RPC uç — `POST /a2a`** (Content-Type: `application/json`)
Gövde JSON-RPC 2.0: `{"jsonrpc":"2.0","id":1,"method":"...","params":{...}}`
Desteklenen methodlar:
- `tasks/send`: `params: {message: {role:"user", parts:[{text:"..."}]}}` →
  `loop_v2.process(text)` senkron çalıştır, dön
  ```json
  {"jsonrpc":"2.0","id":1,"result":{
    "id":"<task_id>","status":"completed","sessionId":"<sid>",
    "artifacts":[{"name":"response","parts":[{"text":"<cevap>"}]}]
  }}
  ```
- `tasks/get`: `params:{id:"<task_id>"}` → kayıtlı task durumunu dön (işleysiz,
  kısa ömürlü in-memory map — kalıcılık gereksiz).
- `tasks/cancel`: bilinmeyen/sefa → `error: {code:-32601, message:"method not implemented"}`.

Bilinmeyen method → JSON-RPC standard error `-32601`.
Geçersiz JSON → `-32700` parse error. Hatalı params → `-32602`.

**3) Auth & güvenlik**
- `verify_token`'ı yeniden kullan: istek header `Authorization: Bearer <token>` VEYA
  `X-Dashboard-Token`: <token>. Auth kapalıysa (is_auth_enabled False) serbest.
- Geoğer/eksik token → HTTP 401 (auth açıkken). İçerik hiçbir zaman `session_manager`
  ham mesajlarını A2A çıktısı olarak sızdırmaz — yalnızca `process()` final metni.
- Rate: kısa senkron `loop.process` — paralel patlama olmasın; basit mutex/queue (tek
  eşzamanlı task) veya per-client basit cooldown. Overengineering YOK.
- `0.0.0.0` üzerinden açma; gateway `127.0.0.1:5792` ile birlikte Ba. Oturum kimliği
  `session_manager` yeni/mevcut session'a yazar, A2A client'a `sessionId` döner.

## Koşullar / anti-regresyon

- Mevcut REST/WebSocket `/api/*`, `/ws/chat`, `/` davranışı DEĞİŞMEZ. Yalnızca
  `/a2a` + `/.well-known/agent.json` EKLENİR.
- Yeni harici Python bağımlılığı YOK (elle JSON-RPC). FastAPI zaten var.
- `loop_v2.process` dışında yeni LLM/agent kalıbı YOK.
- Task ID: `f"task_{uuid4().hex[:12]}"`. Session ID: `session_manager` gerçek ID.
- Streaming `false` ilan (SSE implementasyonu bu task'ta YOK).

## Testler — `tests/gateway/test_a2a.py` (FastAPI TestClient)

1. `GET /.well-known/agent.json` → 200, `name=="Dorina"`, geçerli JSON.
2. `POST /a2a` `tasks/send` okuma → **monkeypatch `loop_v2.process`** ile `"merhaba"`
   → result.status `completed`, artifacts[0].parts[0].text == mock çıktısı.
3. `tasks/get` kaydedilmiş id → completed; bilinmeyen id → eleman error `-32602` veya
   yok (deterministik bir davranış seç).
4. Bilinmeyen method → `-32601`.
5. Geçersiz JSON → `-32700`.
6. Auth açıkken bearer token'suz → 401 (is_auth_enabled monkeypatch True).
7. Regresyon: mevcut 371 test yeşil.

## Kabul (Hermes review)

- [ ] `/a2a` + AgentCard var; eski /api ve /ws bozulmadı
- [ ] tasks/send gerçekten `loop.process` çağırıyor (mock test kanıtlı)
- [ ] JSON-RPC hata kodları standart (-32700/-32602/-32601)
- [ ] auth kapalıysa serbest, açıksa token şart; raw session sızdırmıyor
- [ ] yeni dep yok; 371 + yeni testler yeşil

## Kapsam DIŞI

- A2A **client** tarafı (başka agent'a task atma) / multi-agent — ayrı task
- SSE / streaming (`capabilities.streaming:false` kalır)
- Push notifications / webhook çıkışı
- Kalıcı task deposu (in-memory yeterli)
- resmi `a2a` PyPI paketi bağımlılığı (elle minimal uygulama tercih edilir)