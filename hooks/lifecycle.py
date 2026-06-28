"""Yaşam döngüsü kancaları — pre/post tool events ve hook pipeline.

Pattern: Claude Code Hook Lifecycle + Event Bus Pub/Sub
Her hook bir pipeline aşamasıdır: validation → transform → execute → post-process
"""
from __future__ import annotations
from typing import Callable, Any
from core.logger import log


class HookPipeline:
    """Pre/Post hook pipeline.

    Aşamalar:
      1. pre_execution  → tool çağrısı öncesi validation (False döndürürse iptal)
      2. param_transform → parametreleri değiştirebilir (dict döndürür)
      3. post_processing → sonuç sonrası (result'ı değiştirebilir)
    """

    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {
            "pre_execution": [],
            "param_transform": [],
            "post_processing": [],
        }

    def register(self, stage: str, callback: Callable):
        """Hook kaydet. stage: pre_execution | param_transform | post_processing"""
        if stage in self._hooks:
            self._hooks[stage].append(callback)
            log.debug(f"Hook kaydedildi: stage={stage}, callback={callback.__name__}")
        else:
            log.warning(f"Bilinmeyen hook stage: {stage}")

    def unregister(self, stage: str, callback: Callable):
        """Hook kaldır."""
        if stage in self._hooks:
            self._hooks[stage] = [cb for cb in self._hooks[stage] if cb is not callback]

    def unregister_all(self, stage: str | None = None):
        """Belirli bir stage'deki tüm hook'ları veya tümünü temizle."""
        if stage:
            self._hooks[stage] = []
        else:
            for s in self._hooks:
                self._hooks[s] = []

    def run_pre_execution(self, tool_name: str, arguments: dict) -> bool:
        """Pre-execution validation. False dönerse tool iptal edilir."""
        for cb in self._hooks["pre_execution"]:
            try:
                result = cb(tool_name=tool_name, arguments=arguments)
                if result is False:
                    log.info(f"Pre-execution hook iptal etti: tool={tool_name}, hook={cb.__name__}")
                    return False
            except Exception as e:
                log.warning(f"Pre-execution hook hatası [{cb.__name__}]: {e}")
        return True

    def run_param_transform(self, tool_name: str, arguments: dict) -> dict:
        """Parametre transformasyon zinciri. Her hook dict döndürür."""
        current = dict(arguments)
        for cb in self._hooks["param_transform"]:
            try:
                result = cb(tool_name=tool_name, arguments=current)
                if isinstance(result, dict):
                    current = result
            except Exception as e:
                log.warning(f"Param transform hook hatası [{cb.__name__}]: {e}")
        return current

    def run_post_processing(self, tool_name: str, arguments: dict, result: str) -> str:
        """Post-processing zinciri. Her hook result string döndürür."""
        current = result
        for cb in self._hooks["post_processing"]:
            try:
                new_result = cb(tool_name=tool_name, arguments=arguments, result=current)
                if isinstance(new_result, str):
                    current = new_result
            except Exception as e:
                log.warning(f"Post-processing hook hatası [{cb.__name__}]: {e}")
        return current

    def stage_count(self, stage: str | None = None) -> int:
        """Hook sayısını döndür."""
        if stage:
            return len(self._hooks.get(stage, []))
        return sum(len(v) for v in self._hooks.values())

    def list_hooks(self) -> dict[str, list[str]]:
        """Tüm hook'ları isimleriyle listele."""
        return {
            stage: [cb.__name__ for cb in cbs]
            for stage, cbs in self._hooks.items()
        }


# Global hook pipeline
pipeline = HookPipeline()
