"""
Plugin Template — örnek plugin implementasyonu.

Bu template, Dorina Agent plugin sistemi için başlangıç noktasıdır.
Her plugin bir manifest (plugin.json) ve opsiyonel Python kodu içerir.

Hook'lar:
  on_tool_called(name, arguments)  — tool çağrıldığında tetiklenir
  on_session_start()               — session başladığında tetiklenir
  on_message(role, content)        — her mesajda tetiklenir

Kendi plugin'inizi oluşturmak için:
  1. Bu dizini kopyalayın: cp -r plugins/store/plugin-template plugins/store/my-plugin
  2. plugin.json'u düzenleyin (name, version, hooks, commands)
  3. __init__.py'de hook fonksiyonlarınızı yazın
  4. Agent'ı yeniden başlatın veya plugin'i manuel yükleyin
"""

from core.logger import log


def on_tool_called(event: str, name: str, arguments: dict, **kw):
    """Tool çağrıldığında tetiklenir."""
    log.debug(f"[plugin-template] Tool called: {name}")


def on_session_start(**kw):
    """Session başlangıcında tetiklenir."""
    log.info("[plugin-template] Session started — template plugin active")


def on_message(event: str, role: str, content: str, **kw):
    """Her mesajda tetiklenir."""
    pass  # Örnek: mesajları loglamak için kullanılabilir
