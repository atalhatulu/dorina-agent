"""Metrics testleri."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestMetrics:
    def test_record_increments(self):
        from monitoring.metrics import Metrics
        m = Metrics()
        m.record(tokens=100, cost=0.002)
        assert m.token_count == 100
        assert m.total_cost == 0.002
        assert m.request_count == 1
        assert m.errors == 0

    def test_record_error(self):
        from monitoring.metrics import Metrics
        m = Metrics()
        m.record(error=True)
        assert m.errors == 1
        assert m.request_count == 1

    def test_summary_returns_correct_values(self):
        from monitoring.metrics import Metrics
        m = Metrics()
        m.record(tokens=50, cost=0.001)
        m.record(tokens=150, cost=0.003, error=True)
        s = m.summary()
        assert s["tokens"] == 200
        assert s["cost"] == 0.004
        assert s["requests"] == 2
        assert s["errors"] == 1

    def test_summary_cost_rounding(self):
        from monitoring.metrics import Metrics
        m = Metrics()
        m.record(cost=0.1234567)
        s = m.summary()
        assert s["cost"] == 0.123457  # 6 basamak yuvarlama

    def test_empty_metrics_summary(self):
        from monitoring.metrics import Metrics
        m = Metrics()
        s = m.summary()
        assert s["tokens"] == 0
        assert s["cost"] == 0.0
        assert s["requests"] == 0
        assert s["errors"] == 0
        assert s["total_cost_per_session"] == 0.0
        assert s["session_calls"] == 0

    def test_multiple_records(self):
        from monitoring.metrics import Metrics
        m = Metrics()
        for i in range(10):
            m.record(tokens=10, cost=0.001)
        assert m.token_count == 100
        assert abs(m.total_cost - 0.01) < 1e-9
