"""Değer-Tabanlı Context Puanlama."""

import re

# Modül sabitleri
ELEME_ESIGI = 0.15
MAX_TOKENS_OLD = 8000

# Regex'ler (modül seviyesinde derlenmiş, deterministik)
PATH_REGEX = re.compile(r"(~|/home/[a-zA-Z0-9_.-]+|/[a-zA-Z0-9_./-]+\.(py|sh|md|rs|go))")
CMD_URL_IP_REGEX = re.compile(r"^(curl|ssh|git|pip|docker|npm|sudo)\s|https?://|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", re.MULTILINE)
DECISION_REGEX = re.compile(r"(olacak|karar|yapıldı|tamamlandı|güncellendi|çözüldü)", re.IGNORECASE)

def score_turn(turn: list[dict]) -> float:
    """Tek turn'ün bağlam değeri. 0.0 (önemsiz) – 1.0 (kritik)."""
    if not turn:
        return 0.0
        
    total_score = 0.0
    has_tool_calls = False
    
    for msg in turn:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
            
        if role == "user":
            if len(content) <= 80:
                total_score += 0.1
                
        elif role == "assistant":
            if msg.get("tool_calls"):
                has_tool_calls = True
            
            if not msg.get("tool_calls"):
                if len(content) >= 200 and DECISION_REGEX.search(content):
                    total_score += 0.25
                elif len(content) <= 60:
                    total_score -= 0.05
                    
        elif role == "tool":
            name = msg.get("name", "")
            if name == "read_file":
                total_score += 0.4
            else:
                if has_tool_calls and len(content) > 500:
                    total_score -= 0.15
                if "error" in content.lower() or '"error"' in content:
                    total_score += 0.3

        if PATH_REGEX.search(content):
            total_score += 0.35
        if CMD_URL_IP_REGEX.search(content):
            total_score += 0.3

    return max(0.0, min(1.0, total_score))
