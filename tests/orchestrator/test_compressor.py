import pytest
from orchestrator.compressor import ContextCompressor, COMPRESSION_THRESHOLD, KEEP_LATEST_TURNS, SUMMARY_MAX_CHARS

@pytest.fixture
def compressor():
    return ContextCompressor(max_tokens=1000)

def test_should_compress(compressor):
    # Eşik kontrolü
    messages = [{"role": "user", "content": "test " * 100}]
    # max_tokens=1000, 100 kelime ~100 token, %10 -> compress yapmaz
    assert not compressor.should_compress(messages, turn_count=1)
    
    # max_tokens=1000, 600 kelime ~600 token, %60 -> eşik aşılır, compress yapar
    messages_large = [{"role": "user", "content": "test " * 600}]
    assert compressor.should_compress(messages_large, turn_count=1)

def test_compress_fast_truncation(compressor):
    # Tur sayısını belirleme ve koruma kontrolü
    messages = []
    messages.append({"role": "system", "content": "system prompt"})
    for i in range(10):
        messages.append({"role": "user", "content": f"user {i}"})
        messages.append({"role": "assistant", "content": f"assistant {i}"})
    
    # 10 tur var, son KEEP_LATEST_TURNS (4) korunmalı + system
    compressed = compressor._compress_fast(messages)
    
    assert len(compressed) == 1 + (KEEP_LATEST_TURNS * 2) # system + (user+assistant)*4
    assert compressed[0]["role"] == "system"
    assert compressed[1]["content"] == "user 6"
    assert compressed[-1]["content"] == "assistant 9"

@pytest.mark.asyncio
async def test_compress_llm_fallback(compressor):
    messages = []
    for i in range(10):
        messages.append({"role": "user", "content": f"user {i}"})
        messages.append({"role": "assistant", "content": f"assistant {i}"})
    
    # llm_callback None iken fast truncation çalışmalı
    compressed = await compressor.compress(messages, llm_callback=None, force_tier2=True)
    assert len(compressed) == (KEEP_LATEST_TURNS * 2) # System yok

@pytest.mark.asyncio
async def test_compress_llm(compressor):
    messages = []
    for i in range(10):
        messages.append({"role": "user", "content": f"user {i}"})
        messages.append({"role": "assistant", "content": f"assistant {i}"})
    
    async def mock_llm(prompt):
        return "mock summary"
        
    compressed = await compressor.compress(messages, llm_callback=mock_llm, force_tier2=True)
    
    assert compressed[0]["role"] == "system"
    assert "mock summary" in compressed[0]["content"]
    assert "[Conversation summary #1]" in compressed[0]["content"]
