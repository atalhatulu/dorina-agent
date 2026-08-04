"""Context recall orchestrator logic."""
import re
from core.logger import log

# Sabitler (spec'ten)
RECALL_MIN_WORDS = 6
RECALL_MAX_CHARS = 1500

def should_recall(user_input: str) -> bool:
    """Sorgu hatırlatmaya değer mi?"""
    # Boş veya çok kısa (selam vs.)
    text = user_input.strip()
    words = re.findall(r'\b\w+\b', text)
    
    # 6 kelimeden az ise, geçmiş-imleyici tetikleyiciler var mı diye kontrol et
    past_markers = [
        "ne kadar", "geçen sefer", "gecen sefer", "daha önce", "daha once", 
        "nasıl yapmıştık", "nasil yapmistik", "hatırla", "hatirla", "eski"
    ]
    
    has_marker = any(marker in text.lower() for marker in past_markers)
    
    # Teknik işaretler (dosya, komut)
    has_technical = bool(re.search(r'(/[\w\.-]+|[\w-]+\.py|[\w-]+\.md|python |git |docker )', text))
    
    if len(words) > RECALL_MIN_WORDS and has_marker:
        return True
    if has_marker or has_technical:
        return True
        
    return False

def score_relevance(results: list[dict], user_input: str) -> list[dict]:
    """FTS5 zaten sıralı döner, filtreleme gerekmez."""
    return results

def format_recall(results: list[dict], max_chars: int = RECALL_MAX_CHARS) -> str:
    """'## RECALLED CONTEXT (prev sessions)' blok şablonu."""
    if not results:
        return ""
        
    blocks = []
    current_chars = 0
    
    for r in results:
        snippet = f"- Session '{r['title']}' ({r['timestamp']}) [Role: {r['role']}]: {r['snippet']}"
        
        # Eğer bu bloğu eklemek limiti aşacaksa atla (ya da en düşük puanlı olduğu için döngüyü kır)
        if current_chars + len(snippet) > max_chars and blocks:
            break
            
        blocks.append(snippet)
        current_chars += len(snippet)
        
    if not blocks:
        return ""
        
    return "### RECALLED CONTEXT (prev sessions)\n" + "\n".join(blocks)
