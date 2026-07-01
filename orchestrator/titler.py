"""Session auto-titling — ilk kullanici mesajindan otomatik baslik olusturur."""

from __future__ import annotations
from typing import Optional
import logging


log = logging.getLogger(__name__)


def autotitle(user_input: Optional[str], session_id: Optional[str] = None) -> str:
    """Ilk kullanici mesajindan session basligi olustur.

    Args:
        user_input: Kullanicinin girdigi ilk mesaj.
        session_id: Varsa session ID'si (manager.rename cagrilir).

    Returns:
        Olusturulan baslik (en fazla 60 karakter).
    """
    title = (user_input or "").strip()[:60]
    if title and session_id:
        try:
            from session.manager import manager
            manager.rename(session_id, title)
        except Exception as e:
            log.warning("Session rename failed for %s: %s", session_id, e)
    return title
