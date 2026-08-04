"""Tests for value-based pruning in Tier 1 context compression."""
import pytest
from orchestrator.compressor import ContextCompressor
from orchestrator.value_scorer import score_turn, MAX_TOKENS_OLD

def test_value_scorer_pure():
    """value_scorer saf (deterministic) olmalı ve regex'ler test edilmeli."""
    turn_val = [{"role": "user", "content": "Oku /home/teha/proj/main.py"}]
    turn_noise = [
        {"role": "user", "content": "Command"},
        {"role": "assistant", "tool_calls": [{"id": "1", "name": "tiw"}]},
        {"role": "tool", "name": "tiw", "content": "x" * 600}
    ]
    
    score1 = score_turn(turn_val)
    score2 = score_turn(turn_noise)
    
    assert score1 > score2
    # determinism
    assert score_turn(turn_val) == score_turn(turn_val)

def test_blind_vs_value_pruning():
    """Yaşlı ama değerli (5. turn) korunurken, kör budamada kaybolan senaryo."""
    compressor = ContextCompressor(max_tokens=20000)
    
    messages = [{"role": "system", "content": "Sys"}]
    # Turn 1-4 (eski turnler, normalde atılır)
    for i in range(4):
        messages.append({"role": "user", "content": f"Hi {i}" * 30}) # uzun yap
        messages.append({"role": "assistant", "content": f"Hello {i}" * 30})
        
    # Turn 5 (Kritik eski turn, eleme eşiğini (0.15) geçecek: path regex + short user)
    critical_msg = {"role": "user", "content": "Lütfen /home/teha/proj/main.py dosyasına bak"} # short + path = 0.1 + 0.35 = 0.45
    messages.append(critical_msg)
    messages.append({"role": "assistant", "content": "Tamam bakıyorum."}) # short = -0.05. Total = 0.4
    
    # Turn 6-8 (Gürültü, eski ama değerli değiller)
    for i in range(3):
        messages.append({"role": "user", "content": f"Test {i}" * 30})
        messages.append({"role": "assistant", "content": f"Response {i}" * 30})
        
    # Son 4 Turn (keep_latest_turns)
    for i in range(4):
        messages.append({"role": "user", "content": f"Recent {i}"})
        messages.append({"role": "assistant", "content": f"Recent {i}"})
        
    compressed = compressor._compress_fast(messages)
    
    # System should be kept
    assert any(m.get("role") == "system" for m in compressed)
    
    # Critical message from turn 5 should be kept
    assert any("main.py" in str(m.get("content", "")) for m in compressed)

def test_noise_pruning():
    """Uzun çıktılı, değeri düşük tool'lar önce silinir."""
    compressor = ContextCompressor(max_tokens=20000)
    messages = [{"role": "system", "content": "Sys"}]
    
    # Eski turn'lere bir gürültü bir değerli koy
    # Gürültü turn:
    messages.extend([
        {"role": "user", "content": "Run tool"},
        {"role": "assistant", "tool_calls": [{"id": "1", "name": "tiw"}]},
        {"role": "tool", "name": "tiw", "content": "noisy " * 200}
    ])
    
    # Değerli turn (read_file = +0.4)
    messages.extend([
        {"role": "user", "content": "Read file"},
        {"role": "assistant", "tool_calls": [{"id": "2", "name": "read_file"}]},
        {"role": "tool", "name": "read_file", "content": "important data"}
    ])
    
    # Son 4 turn
    for i in range(4):
        messages.extend([{"role": "user", "content": f"T{i}"}, {"role": "assistant", "content": f"R{i}"}])
        
    compressed = compressor._compress_fast(messages)
    
    # read_file should be kept
    assert any("important data" in str(m.get("content", "")) for m in compressed)
    
    # noisy tool should be pruned
    assert not any("noisy noisy" in str(m.get("content", "")) for m in compressed)

def test_system_protection():
    """System mesajı her zaman korunur."""
    compressor = ContextCompressor(max_tokens=20000)
    messages = [{"role": "system", "content": "MUST_KEEP_SYSTEM"}]
    for i in range(10):
        messages.extend([{"role": "user", "content": f"U{i}"}, {"role": "assistant", "content": f"A{i}"}])
        
    compressed = compressor._compress_fast(messages)
    assert compressed[0]["role"] == "system"
    assert compressed[0]["content"] == "MUST_KEEP_SYSTEM"

def test_token_limit():
    """Eski turn token toplamı MAX_TOKENS_OLD'u aşmamalı."""
    from core.tokenizer import count_messages_tokens
    
    compressor = ContextCompressor(max_tokens=20000)
    messages = [{"role": "system", "content": "Sys"}]
    
    for i in range(15):
        messages.extend([
            {"role": "user", "content": "Read file"},
            {"role": "assistant", "tool_calls": [{"id": f"{i}", "name": "read_file"}]},
            {"role": "tool", "name": "read_file", "content": "huge data " * 500} # roughly 1000 tokens
        ])
        
    for i in range(4):
        messages.extend([{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}])
        
    compressed = compressor._compress_fast(messages)
    
    turns = compressor._split_into_turns(compressed)
    
    # Son 4'ü hariç tut, system'i hariç tut
    old_turns = [t for t in turns[:-4] if not (t and t[0].get("role") == "system")]
    
    old_tokens = 0
    for t in old_turns:
        old_tokens += count_messages_tokens(t)
        
    assert old_tokens <= MAX_TOKENS_OLD

def test_edge_cases():
    """Tek turn, boş giriş, vb."""
    compressor = ContextCompressor()
    assert compressor._compress_fast([]) == []
    
    single = [{"role": "user", "content": "hi"}]
    assert compressor._compress_fast(single) == single
