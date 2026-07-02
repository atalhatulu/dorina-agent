"""
Tool schema secici — LLM'in hangi tool'lari gorecegini belirler.

STRATEJI: Kullanici mesajini analiz et, ihtiyac duyulan tool kategorilerini
tespit et, sadece onlari gonder. Her turda ~8-12 tool (25 degil).
"""

from __future__ import annotations

# ── Her durumda giden temel tool'lar (4-5 tool) ──
# Dosya okuma, arama, terminal, web. LLM'in ise baslamasi icin yeterli.
CORE_TOOLS = frozenset({
    "terminal", "read_file", "search_files", "web_search", "patch",
})

# ── Kategoriler ──
# Her kategori: (tetikleyici_kelimeler, tool_seti)
# Kullanici mesajinda tetikleyici kelime gecerse o kategorideki tool'lar eklenir.
CATEGORIES: list[tuple[frozenset[str], frozenset[str]]] = [
    # Kod/duzeltme: dosya yazma, yamalama, toplu islem
    (
        frozenset({"yaz", "duzelt", "guncelle", "refactor", "patch", "olustur",
                    "ekle", "kaldir", "sil", "degistir", "fix", "bug", "hata",
                    "sorun", "calismiyor", "bozuk", "problem"}),
        frozenset({"write_file", "patch", "batch_python"}),
    ),
    # Git: versiyon kontrol
    (
        frozenset({"git", "commit", "push", "pull", "merge", "branch"}),
        frozenset({"git_add", "git_branch", "git_commit", "git_diff", "git_push"}),
    ),
    # Arastirma: web'de arama, detayli inceleme
    (
        frozenset({"arastir", "incele", "ogren", "bul", "nedir", "kimdir",
                    "nasil", "arama", "sorun", "hatali", "calismiyor"}),
        frozenset({"web_search", "web_fetch"}),
    ),
    # Hafiza: kaydet, hatirla
    (
        frozenset({"kaydet", "hatirla", "ogren", "unutma", "hafiza", "skill"}),
        frozenset({"save_memory", "read_memory"}),
    ),
    # Proje/dizin kesfi
    (
        frozenset({"proje", "klasor", "dizin", "dosya yapisi", "nerede"}),
        frozenset({"search_files", "read_file", "terminal"}),
    ),
]

# ── Yonetim tool'lari (sadece acikca istenince) ──
# Kullanici /komut ile veya dogrudan isim vererek cagirir.
MANAGEMENT_TOOLS = frozenset({
    "clarify", "cron", "timer", "uuid_generate", "analyze_image",
    "list_providers", "switch_provider", "tools_enable",
    "cancel_background", "list_background", "graphify",
    "save_memory", "read_memory",
})

# ── Agir tool'lar (sadece acikca istenince) ──
HEAVY_TRIGGERS: dict[str, tuple[str, ...]] = {
    "browser_navigate": ("web sayfasi", "siteye git", "browser", "url ac", "html sayfa"),
    "image_generate": ("resim olustur", "foto uret", "gorsel olustur", "illustrasyon"),
    "text_to_speech": ("ses", "konus", "oku sesli", "voice", "konusma"),
    "delegate_task": ("alt gorev", "subagent", "delege", "paralel"),
    "delegate_batch": ("toplu gorev", "batch gorev", "coklu gorev"),
    "deep_research": ("derin arastirma", "detayli arastirma", "kapsamli arastirma"),
    "sandbox_exec": ("guvenli calistir", "sandbox", "docker ile calistir"),
    "mcp_call_tool": ("mcp", "ozel arac"),
}


def _normalize(text: str) -> str:
    """Türkçe karakterleri ASCII'ye çevir, küçük harf yap."""
    replacements = {
        'ü': 'u', 'ğ': 'g', 'ş': 's', 'ı': 'i', 'ö': 'o', 'ç': 'c',
        'Ü': 'u', 'Ğ': 'g', 'Ş': 's', 'İ': 'i', 'Ö': 'o', 'Ç': 'c',
    }
    result = text.lower()
    for tr, en in replacements.items():
        result = result.replace(tr, en)
    return result


def select_schemas(user_input: str, registry=None) -> list[str]:
    """Kullanici girdisine gore hangi tool'lari gonderecegini belirler.

    1. CORE: 4-5 temel tool her zaman gider
    2. KATEGORI: mesajdaki anahtar kelimelere gore ek tool'lar
    3. YONETIM: kullanici acikca isterse eklenir
    4. AGIR: sadece net trigger ile

    Toplamda her turda ~8-12 tool.
    """
    tools = set(CORE_TOOLS)
    text = _normalize(user_input)
    words = set(text.split())

    # Kategori bazli eslestirme (normalize edilmis metin ile)
    for keywords, tool_set in CATEGORIES:
        if any(k in text for k in keywords):
            tools.update(tool_set)

    # Yonetim tool'lari — kullanici /komut veya dogrudan isimle cagirirsa ekle
    # (cogunlukla gerekmez ama LLM bilincinde olsun)
    _mgmt_signals = {"zamanla", "hatirlat", "kronometre", "uuid", "uret",
                     "provider", "saglayici", "tool aktif", "tool ac",
                     "graf", "graphify", "baglanti", "modul"}
    if any(w in words for w in _mgmt_signals):
        tools.update(MANAGEMENT_TOOLS)

    # Agir tool'lar — sadece net trigger ile
    for tool_name, triggers in HEAVY_TRIGGERS.items():
        if any(t in text for t in triggers):
            tools.add(tool_name)

    # Kayitli olmayan tool'lari filtrele
    if registry is not None:
        registered = {t.name for t in registry.list()}
        tools &= registered

    return list(tools)
