"""Tests for Task system."""
import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from agents.task_runner import TaskRunner, TaskStatus, TaskType


class TestTaskRunner:
    def test_create_task(self):
        """Task oluşturma."""
        r = TaskRunner()
        t = r.create("local_bash", "echo test")
        assert t.id is not None
        assert t.status == TaskStatus.PENDING
        assert t.goal == "echo test"

    def test_task_lifecycle(self):
        """Task yaşam döngüsü."""
        r = TaskRunner()
        t = r.create("local_agent", "research python")
        assert r.start(t.id) == True
        assert t.status == TaskStatus.RUNNING
        r.complete(t.id, "Python 3.14")
        assert t.status == TaskStatus.COMPLETED
        assert t.result == "Python 3.14"

    def test_task_fail(self):
        """Task hatası."""
        r = TaskRunner()
        t = r.create("local_bash", "invalid command !@#")
        r.start(t.id)
        r.fail(t.id, "Command not found")
        assert t.status == TaskStatus.FAILED
        assert "not found" in t.error

    def test_task_kill(self):
        """Task iptali."""
        r = TaskRunner()
        t = r.create("monitor", "watch disk")
        r.start(t.id)
        r.kill(t.id)
        assert t.status == TaskStatus.KILLED

    def test_task_list(self):
        """Task listeleme."""
        r = TaskRunner()
        r.create("local_bash", "cmd1")
        r.create("local_bash", "cmd2")
        task_list = r.list()
        assert len(task_list) == 2
        assert task_list[0]["goal"] == "cmd2" or task_list[0]["goal"] == "cmd1"

    def test_task_list_filtered(self):
        """Filtreli task listeleme."""
        r = TaskRunner()
        t = r.create("local_bash", "will fail")
        r.start(t.id)
        r.fail(t.id, "error")
        pending = r.list(status="pending")
        failed = r.list(status="failed")
        assert len(pending) == 0
        assert len(failed) >= 1

    def test_task_stats(self):
        """Task istatistikleri."""
        r = TaskRunner()
        r.create("local_bash", "c1")
        r.create("local_agent", "c2")
        s = r.stats()
        assert s["total"] == 2
        assert s["by_status"]["pending"] == 2
