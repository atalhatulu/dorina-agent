"""
Dorina Agent — E-posta (IMAP/SMTP) modülü.

Odysseus email_poller pattern:
- Async IMAP IDLE polling arka planda e-postaları dinler
- Gelen e-postalar event_bus üzerinden yayınlanır
- SMTP üzerinden gönderme işlemi senkron/async destekler

Kullanım:
    from mail.client import email_client
    await email_client.send("user@example.com", "Merhaba", "İçerik")
    mails = await email_client.read_inbox(limit=5)
"""

from __future__ import annotations
from mail.client import EmailClient, EmailPoller, email_client, email_poller

__all__ = ["EmailClient", "EmailPoller", "email_client", "email_poller"]
