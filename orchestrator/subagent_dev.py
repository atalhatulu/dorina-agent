"""Subagent-Driven Development — implementer + reviewer pipeline.

Superpowers pattern: önce test yaz, sonra implemente et.
Pipeline: spec → test → implement → review → merge

Akış:
  1. Analyst: spec'i analiz eder, test planı çıkarır
  2. TestWriter: test planına göre test yazar (önce test!)
  3. Implementer: test geçecek şekilde kodu yazar
  4. Reviewer: implementasyonu gözden geçirir
  5. Merger: onaylanan değişiklikleri birleştirir
"""

from __future__ import annotations
import json
import time
import uuid
import traceback
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path

from core.logger import log
from core.event_bus import bus
from tools.delegate import SubAgent, delegate


# ── Pipeline stages ────────────────────────────────────────

class DevStage:
    ANALYST = "analyst"
    TEST_WRITER = "test_writer"
    IMPLEMENTER = "implementer"
    REVIEWER = "reviewer"
    MERGER = "merger"


# ── Data models ────────────────────────────────────────────

@dataclass
class DevTask:
    """Bir geliştirme görevi."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    spec: str = ""
    test_plan: str = ""
    test_code: str = ""
    implementation: str = ""
    review_result: str = ""
    review_score: int = 0
    files_modified: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, testing, implementing, reviewing, approved, rejected, done
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class DevSession:
    """Geliştirme oturumu."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    goal: str = ""
    tasks: list[DevTask] = field(default_factory=list)
    status: str = "running"
    created_at: float = field(default_factory=time.time)


# ── Subagent implementations ───────────────────────────────

class AnalystAgent:
    """Analiz aşaması: spec'i analiz eder, test planı çıkarır."""

    @staticmethod
    def analyze(spec: str, file_list: list[str] | None = None) -> str:
        """Spec'i analiz et ve test planı oluştur."""
        files_info = f"\nMevcut dosyalar: {', '.join(file_list)}" if file_list else ""
        prompt = (
            f"Görev: Verilen spec'i analiz et ve kapsamlı bir test planı çıkar.\n\n"
            f"SPEC:\n{spec}\n{files_info}\n\n"
            f"Lütfen şunları belirle:\n"
            f"1. Hangi dosyalar değişecek / oluşturulacak\n"
            f"2. Hangi testler yazılmalı (fonksiyon bazında)\n"
            f"3. Test senaryoları (başarılı, hata, edge case)\n"
            f"4. Implementasyon adımları\n\n"
            f"Test planı formatı:\n"
            f"## Test Planı\n"
            f"- **Dosya**: path/to/file.py\n"
            f"  - Test: test_function_name - açıklama\n"
            f"- **Edge Cases**: ...\n"
        )

        agent = SubAgent(goal=prompt, context="Sen bir yazılım analistisin.")
        result = agent.run()
        return str(result)


class TestWriterAgent:
    """Test yazma aşaması: önce test yaz, sonra implemente et."""

    @staticmethod
    def write_tests(test_plan: str, target_file: str) -> str:
        """Test planına göre pytest test'leri yaz."""
        prompt = (
            f"Görev: Aşağıdaki test planına göre pytest testleri yaz.\n"
            f"HEDEF: ÖNCE TEST YAZ, sonra implementasyon yapılacak.\n\n"
            f"TEST PLANI:\n{test_plan}\n\n"
            f"Hedef dosya: {target_file}\n\n"
            f"Kurallar:\n"
            f"1. test_ prefix'li fonksiyonlar yaz\n"
            f"2. pytest kullan\n"
            f"3. Edge case'leri kapsa\n"
            f"4. Mock'lama gerekiyorsa unittest.mock kullan\n"
            f"5. Testler çalıştırılabilir olmalı\n\n"
            f"Sadece test kodunu döndür (markdown code block içinde)."
        )

        agent = SubAgent(goal=prompt, context="Sen bir test mühendisisin. Önce test yaz, sonra kod.")
        result = agent.run()
        return str(result)


class ImplementerAgent:
    """Implementasyon aşaması: test geçecek şekilde kodu yaz."""

    @staticmethod
    def implement(spec: str, test_code: str, target_file: str) -> str:
        """Test geçecek şekilde implementasyon yaz."""
        prompt = (
            f"Görev: Aşağıdaki spec ve test koduna göre implementasyon yaz.\n"
            f"Testlerin TAMAMINI geçecek şekilde kod yazmalısın.\n\n"
            f"SPEC:\n{spec}\n\n"
            f"HEDEF DOSYA: {target_file}\n\n"
            f"TEST KODU:\n{test_code}\n\n"
            f"Kurallar:\n"
            f"1. Tüm testleri geçecek implementasyon yaz\n"
            f"2. Kod temiz ve okunabilir olmalı\n"
            f"3. Tip ipuçları (type hints) ekle\n"
            f"4. Docstring ekle\n"
            f"5. import'ları doğru yap\n\n"
            f"Sadece implementasyon kodunu döndür (markdown code block içinde)."
        )

        agent = SubAgent(goal=prompt, context="Sen bir Python geliştiricisin. Test-driven development yapıyorsun.")
        result = agent.run()
        return str(result)


class ReviewerAgent:
    """Review aşaması: implementasyonu gözden geçir."""

    @staticmethod
    def review(spec: str, test_code: str, implementation: str) -> dict:
        """Implementasyonu review et ve puan ver."""
        prompt = (
            f"Görev: Aşağıdaki implementasyonu code review yap.\n\n"
            f"SPEC:\n{spec}\n\n"
            f"TEST KODU:\n{test_code}\n\n"
            f"IMPLEMENTASYON:\n{implementation}\n\n"
            f"Değerlendirme kriterleri (1-10):\n"
            f"1. Doğruluk: Spec'e uygun mu?\n"
            f"2. Test Coverage: Testler yeterli mi?\n"
            f"3. Kod Kalitesi: Temiz, okunabilir, tip güvenli mi?\n"
            f"4. Performans: Verimli mi?\n"
            f"5. Güvenlik: Güvenlik açığı var mı?\n\n"
            f"Format:\n"
            f"## Review Sonucu\n"
            f"**Puan**: X/10\n"
            f"**Doğruluk**: X/10 - açıklama\n"
            f"**Test Coverage**: X/10 - açıklama\n"
            f"**Kod Kalitesi**: X/10 - açıklama\n"
            f"**Performans**: X/10 - açıklama\n"
            f"**Güvenlik**: X/10 - açıklama\n"
            f"**Onay**: EVET/HAYIR\n"
            f"**Yorumlar**: ...\n"
        )

        agent = SubAgent(goal=prompt, context="Sen bir kıdemli code reviewer'sın.")
        result = str(agent.run())

        # Extract score from review
        score = 0
        for line in result.split("\n"):
            if "**Puan**" in line:
                try:
                    score_str = line.split("**Puan**")[-1].strip().split("/")[0]
                    score = int(score_str)
                except (ValueError, IndexError):
                    score = 5  # Default

        return {
            "review": result,
            "score": score,
            "approved": score >= 7,
        }


# ── Pipeline orchestrator ──────────────────────────────────

class DevPipeline:
    """Subagent-driven development pipeline."""

    def __init__(self):
        self.active_sessions: dict[str, DevSession] = {}

    def create_session(self, goal: str) -> str:
        """Yeni geliştirme oturumu başlat. Session ID döndürür."""
        session = DevSession(goal=goal)
        self.active_sessions[session.id] = session
        bus.publish("dev:session_started", session_id=session.id, goal=goal)
        log.info(f"Dev session started: {session.id} — {goal[:60]}")
        return session.id

    def run_pipeline(self, session_id: str, spec: str,
                     file_list: list[str] | None = None,
                     target_file: str = "") -> DevTask:
        """Tam pipeline'ı çalıştır: analyst → test → implement → review."""
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        task = DevTask(spec=spec)
        session.tasks.append(task)

        try:
            # Stage 1: Analyst
            log.info(f"[{task.id}] Stage: ANALYST")
            bus.publish("dev:stage_started", task_id=task.id, stage="analyst")
            task.test_plan = AnalystAgent.analyze(spec, file_list)
            task.status = "testing"
            bus.publish("dev:stage_completed", task_id=task.id, stage="analyst")

            # Stage 2: Test Writer (önce test!)
            log.info(f"[{task.id}] Stage: TEST_WRITER")
            bus.publish("dev:stage_started", task_id=task.id, stage="test_writer")
            task.test_code = TestWriterAgent.write_tests(task.test_plan, target_file)
            task.status = "implementing"
            bus.publish("dev:stage_completed", task_id=task.id, stage="test_writer")

            # Stage 3: Implementer
            log.info(f"[{task.id}] Stage: IMPLEMENTER")
            bus.publish("dev:stage_started", task_id=task.id, stage="implementer")
            task.implementation = ImplementerAgent.implement(spec, task.test_code, target_file)
            task.status = "reviewing"
            bus.publish("dev:stage_completed", task_id=task.id, stage="implementer")

            # Stage 4: Reviewer
            log.info(f"[{task.id}] Stage: REVIEWER")
            bus.publish("dev:stage_started", task_id=task.id, stage="reviewer")
            review_data = ReviewerAgent.review(spec, task.test_code, task.implementation)
            task.review_result = review_data["review"]
            task.review_score = review_data["score"]

            if review_data["approved"]:
                task.status = "approved"
                log.info(f"[{task.id}] Review APPROVED (score: {task.review_score})")
            else:
                task.status = "rejected"
                log.warning(f"[{task.id}] Review REJECTED (score: {task.review_score})")

            task.completed_at = time.time()
            bus.publish("dev:task_completed", task_id=task.id, status=task.status,
                        score=task.review_score)

        except Exception as e:
            task.status = "error"
            task.error = str(e)
            log.error(f"[{task.id}] Pipeline error: {e}\n{traceback.format_exc()}")
            bus.publish("dev:task_error", task_id=task.id, error=str(e))

        return task

    def get_session(self, session_id: str) -> Optional[DevSession]:
        """Session detayı."""
        return self.active_sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        """Aktif session'ları listele."""
        return [
            {
                "id": s.id,
                "goal": s.goal[:50],
                "task_count": len(s.tasks),
                "status": s.status,
                "created": s.created_at,
            }
            for s in self.active_sessions.values()
        ]

    def get_task(self, session_id: str, task_id: str) -> Optional[DevTask]:
        """Task detayı."""
        session = self.active_sessions.get(session_id)
        if not session:
            return None
        for t in session.tasks:
            if t.id == task_id:
                return t
        return None

    def cleanup(self, max_age_hours: int = 24):
        """Eski session'ları temizle."""
        cutoff = time.time() - (max_age_hours * 3600)
        self.active_sessions = {
            k: v for k, v in self.active_sessions.items()
            if v.created_at > cutoff
        }


# Global instance
dev_pipeline = DevPipeline()
