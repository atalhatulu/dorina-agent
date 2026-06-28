"""
E-posta istemcisi — IMAP okuma + SMTP gönderme.
Odysseus email_poller pattern:
- EmailPoller: IMAP IDLE ile arka planda e-posta dinleme
- EmailClient: SMTP gönderme + IMAP okuma
"""

from __future__ import annotations
import asyncio
import os
import time
import json
from pathlib import Path
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Optional
from core.logger import log
from core.config import settings


# ═══════════════════════════════════════════════════════════════
# EmailClient — Gönderme ve Okuma
# ═══════════════════════════════════════════════════════════════

class EmailClient:
    """SMTP gönderme + IMAP okuma."""

    def __init__(self):
        self.imap_server = os.environ.get("IMAP_SERVER", getattr(settings, 'mail', None) and getattr(settings.mail, 'imap_server', "") or "")
        self.smtp_server = os.environ.get("SMTP_SERVER", getattr(settings, 'mail', None) and getattr(settings.mail, 'smtp_server', "") or "")
        self.email_addr = os.environ.get("EMAIL_ADDR", getattr(settings, 'mail', None) and getattr(settings.mail, 'email_addr', "") or "")
        self.email_pass = os.environ.get("EMAIL_PASS", getattr(settings, 'mail', None) and getattr(settings.mail, 'email_pass', "") or "")
        self.imap_port = int(os.environ.get("IMAP_PORT", getattr(settings, 'mail', None) and getattr(settings.mail, 'imap_port', 993) or 993))
        self.smtp_port = int(os.environ.get("SMTP_PORT", getattr(settings, 'mail', None) and getattr(settings.mail, 'smtp_port', 587) or 587))

    @property
    def configured(self) -> bool:
        """Tüm ayarlar mevcut mu?"""
        return bool(self.imap_server and self.smtp_server and self.email_addr and self.email_pass)

    # ── SMTP Gönderme ──────────────────────────────────────

    def send(self, to: str, subject: str, body: str) -> bool:
        """E-posta gönder (senkron)."""
        if not all([self.smtp_server, self.email_addr, self.email_pass]):
            log.warning("SMTP ayarlari eksik (config.yaml veya .env)")
            return False
        try:
            import smtplib
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = subject
            msg["From"] = self.email_addr
            msg["To"] = to
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as s:
                s.starttls()
                s.login(self.email_addr, self.email_pass)
                s.send_message(msg)
            log.info(f"Email gonderildi: {to} -> {subject}")
            return True
        except Exception as e:
            log.error(f"Email gonderilemedi: {e}")
            return False

    async def send_async(self, to: str, subject: str, body: str) -> bool:
        """E-posta gönder (async — loop'u bloklamaz)."""
        return await asyncio.to_thread(self.send, to, subject, body)

    # ── IMAP Okuma ─────────────────────────────────────────

    def read_inbox(self, limit: int = 10, folder: str = "INBOX") -> list[dict]:
        """Gelen kutusundan e-postaları oku."""
        if not all([self.imap_server, self.email_addr, self.email_pass]):
            log.warning("IMAP ayarlari eksik")
            return []
        try:
            import imaplib
            import email
            mails = []
            with imaplib.IMAP4_SSL(self.imap_server, self.imap_port) as imap:
                imap.login(self.email_addr, self.email_pass)
                imap.select(folder)
                _, data = imap.search(None, "ALL")
                if not data[0]:
                    return []
                for num in data[0].split()[-limit:]:
                    _, msg_data = imap.fetch(num, "(RFC822)")
                    if msg_data[0] is None:
                        continue
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8", errors="replace")
                    # Body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                charset = part.get_content_charset() or "utf-8"
                                try:
                                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                                except Exception:
                                    body = str(part.get_payload())
                                break
                    else:
                        charset = msg.get_content_charset() or "utf-8"
                        try:
                            body = msg.get_payload(decode=True).decode(charset, errors="replace")
                        except Exception:
                            body = str(msg.get_payload())

                    # From'u decode et
                    from_header = msg["From"]
                    if from_header:
                        from_parts = decode_header(from_header)
                        from_name = ""
                        for part, enc in from_parts:
                            if isinstance(part, bytes):
                                from_name += part.decode(enc or "utf-8", errors="replace")
                            else:
                                from_name += str(part)
                        from_header = from_name

                    mails.append({
                        "id": num.decode() if isinstance(num, bytes) else str(num),
                        "from": from_header,
                        "subject": subject,
                        "date": msg["Date"],
                        "body_preview": body[:500] if body else "",
                        "has_attachments": msg.is_multipart() and any(
                            p.get_content_maintype() != "text" for p in msg.walk()
                        ),
                    })
            return mails
        except Exception as e:
            log.error(f"Email okunamadi: {e}")
            return []

    async def read_inbox_async(self, limit: int = 10, folder: str = "INBOX") -> list[dict]:
        """Async inbox okuma."""
        return await asyncio.to_thread(self.read_inbox, limit, folder)

    def search_emails(self, query: str, folder: str = "INBOX", limit: int = 20) -> list[dict]:
        """E-postalarda ara (IMAP SEARCH)."""
        if not all([self.imap_server, self.email_addr, self.email_pass]):
            return []
        try:
            import imaplib
            import email
            mails = []
            with imaplib.IMAP4_SSL(self.imap_server, self.imap_port) as imap:
                imap.login(self.email_addr, self.email_pass)
                imap.select(folder)
                # Search FROM, SUBJECT, BODY
                _, data = imap.search(None, f'OR FROM "{query}" OR SUBJECT "{query}" BODY "{query}"')
                if not data[0]:
                    return []
                for num in data[0].split()[-limit:]:
                    _, msg_data = imap.fetch(num, "(RFC822)")
                    if msg_data[0] is None:
                        continue
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8", errors="replace")
                    mails.append({
                        "id": num.decode() if isinstance(num, bytes) else str(num),
                        "from": msg["From"],
                        "subject": subject,
                        "date": msg["Date"],
                    })
            return mails
        except Exception as e:
            log.error(f"Email arama hatasi: {e}")
            return []

    # ── E-posta detayı ─────────────────────────────────────

    def read_email_detail(self, email_id: str, folder: str = "INBOX") -> Optional[dict]:
        """Belirli bir e-postanın tam detayını oku."""
        if not all([self.imap_server, self.email_addr, self.email_pass]):
            return None
        try:
            import imaplib
            import email
            with imaplib.IMAP4_SSL(self.imap_server, self.imap_port) as imap:
                imap.login(self.email_addr, self.email_pass)
                imap.select(folder)
                _, msg_data = imap.fetch(email_id.encode(), "(RFC822)")
                if msg_data[0] is None:
                    return None
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding or "utf-8", errors="replace")

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            charset = part.get_content_charset() or "utf-8"
                            try:
                                body = part.get_payload(decode=True).decode(charset, errors="replace")
                            except Exception:
                                body = str(part.get_payload())
                            break
                else:
                    charset = msg.get_content_charset() or "utf-8"
                    try:
                        body = msg.get_payload(decode=True).decode(charset, errors="replace")
                    except Exception:
                        body = str(msg.get_payload())

                return {
                    "id": email_id,
                    "from": msg["From"],
                    "to": msg["To"],
                    "cc": msg["CC"],
                    "subject": subject,
                    "date": msg["Date"],
                    "body": body,
                }
        except Exception as e:
            log.error(f"Email detay okunamadi: {e}")
            return None


# ═══════════════════════════════════════════════════════════════
# EmailPoller — Odysseus Pattern: Arka planda IMAP IDLE polling
# ═══════════════════════════════════════════════════════════════

class EmailPoller:
    """
    Arka planda IMAP IDLE ile yeni e-postaları dinler.
    Odysseus pattern: poller.poll() bir asyncio task'i olarak run loop'a eklenir.
    Gelen her yeni e-posta için callback çağrılır.
    """

    def __init__(self, check_interval: int = 30, callback=None):
        self.client = email_client
        self.check_interval = check_interval
        self.callback = callback or self._default_callback
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._last_checked: Optional[str] = None

    async def poll(self):
        """Ana polling döngüsü — asyncio task olarak başlatılmalı."""
        if not self.client.configured:
            log.warning("EmailPoller: Mail ayarlari eksik, polling baslatilamadi")
            return

        self.running = True
        log.info(f"EmailPoller baslatildi (interval={self.check_interval}s)")

        try:
            while self.running:
                try:
                    mails = await self.client.read_inbox_async(limit=5)
                    if mails:
                        latest = mails[0]
                        if self._last_checked is None or latest["id"] != self._last_checked:
                            self._last_checked = latest["id"]
                            await self.callback(latest)
                except Exception as e:
                    log.error(f"EmailPoller polling hatasi: {e}")

                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            log.info("EmailPoller durduruldu")
        finally:
            self.running = False

    async def _default_callback(self, email_data: dict):
        """Varsayılan callback — event_bus üzerinden yayınla."""
        try:
            from core.event_bus import bus
            await bus.emit("email:received", email_data)
            log.info(f"EmailPoller: Yeni e-posta -> {email_data.get('subject', '')}")
        except Exception as e:
            log.error(f"EmailPoller callback hatasi: {e}")

    def start(self):
        """Polling'i arka planda başlat."""
        if self._task and not self._task.done():
            log.warning("EmailPoller zaten calisiyor")
            return
        self._task = asyncio.create_task(self.poll())

    def stop(self):
        """Polling'i durdur."""
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None


# ═══════════════════════════════════════════════════════════════
# Singleton'lar
# ═══════════════════════════════════════════════════════════════

email_client = EmailClient()
email_poller = EmailPoller()
