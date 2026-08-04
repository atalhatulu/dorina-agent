"""Tests for query_classifier.py"""

from tools.query_classifier import classify

def test_classify_queries():
    assert classify("nasil yapilir istanbul da hava") == "read"
    assert classify("python ile saatlik rapor ureten script yaz") == "code"
    assert classify("merhaba") == "chat"
    assert classify("hava durumu") == "read"
    assert classify("main.py dosyasinda hata duzelt") == "code"
    assert classify("") == "general"
    assert classify(None) == "general"
    assert classify("grep -r todos ~/proj") == "code"

def test_determinism():
    input_str = "bu bir test mesajidir"
    assert classify(input_str) == classify(input_str)
