"""3 katmanli tool schema secici — token tasarrufu icin.

Katman 1 — CORE: her zaman gider (5-6 tool)
Katman 2 — CONTEXT: goreve gore eklenir (5-10 tool)
Katman 3 — ON_DEMAND: sadece acikca istenince
"""

from __future__ import annotations

# ── Katman 1: Her zaman giden tool'lar ──
CORE_TOOLS = frozenset({
    "terminal", "read_file", "write_file",
    "web_search", "patch", "search_files",
})

# ── Katman 2: Gorev kategorileri ──
CONTEXT_RULES: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "git": (
        frozenset({"git", "commit", "branch", "push", "pull", "merge", "diff", "log", "status"}),
        frozenset({"git_diff", "git_log", "git_status"}),
    ),
    "research": (
        frozenset({"arastir", "incele", "analiz", "bul", "nedir", "kimdir", "arama", "ogren"}),
        frozenset({"web_fetch", "read_file"}),
    ),
    "memory": (
        frozenset({"hatirla", "kaydet", "ogren", "skill", "hafiza", "unutma"}),
        frozenset({"memory"}),
    ),
    "graph": (
        frozenset({"graphify", "baglanti", "modul", "import", "grafik"}),
        frozenset({"graphify"}),
    ),
    "background": (
        frozenset({"arka plan", "background", "dinle", "izle", "tara", "bekle", "indir"}),
        frozenset({"terminal"}),
    ),
    "code": (
        frozenset({"kod", "yaz", "duzelt", "guncelle", "refactor", "debug", "hata", "calistir", "test"}),
        frozenset({"read_file", "write_file", "patch", "terminal", "search_files"}),
    ),
    "project": (
        frozenset({"proje", "uygulama", "dizin", "klasor", "dosya"}),
        frozenset({"search_files", "read_file"}),
    ),
}

# ── Katman 3: Sadece acikca istenince ──
ONDEMAND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "image_generate": ("resim", "foto", "gorsel", "illustrasyon", "art", "gif"),
    "text_to_speech": ("ses", "konus", "oku sesli", "voice"),
    "vision_analyze": ("goruntu", "ekran goruntusu", "fotograf", "resme bak"),
    "browser_navigate": ("web sayfasi", "siteye git", "browser", "url ac"),
    "email": ("eposta", "mail", "posta"),
    "delegate_task": ("alt gorev", "subagent", "delege", "paralel"),
    "cronjob": ("zamanla", "periyodik", "her gun", "cron"),
    "image_generate": ("resim olustur", "foto uret", "goruntu olustur"),
}


def select_schemas(user_input: str, registry=None) -> list[str]:
    """Kullanici girdisine gore hangi tool'lari gonderecegini belirler.

    Args:
        user_input: Kullanici mesaji.
        registry: Opsiyonel ToolRegistry. Verilirse sadece kayitli tool'lar doner.

    Returns:
        Tool isimlerinin listesi.
    """
    tools = set(CORE_TOOLS)
    text = user_input.lower()

    # Katman 2: Context eslestir
    for _category, (keywords, tool_set) in CONTEXT_RULES.items():
        if any(k in text for k in keywords):
            tools.update(tool_set)

    # Katman 3: On-demand kontrol
    for tool_name, triggers in ONDEMAND_KEYWORDS.items():
        if any(t in text for t in triggers):
            tools.add(tool_name)

    # Kayitli olmayan tool'lari filtrele
    if registry is not None:
        registered = {t.name for t in registry.list()}
        tools &= registered

    return list(tools)
