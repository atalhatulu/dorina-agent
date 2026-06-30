"""Checkpoint/Snapshot sistemi — agent durumunu kaydet ve geri yükle.

Her N adımda otomatik checkpoint, manuel snapshot komutu ile anlık görüntü.
Checkpoint'ler JSON formatında data/checkpoints/ altında saklanır.
"""

from __future__ import annotations
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

from core.logger import log

from core.constants import DEFAULT_DATA_DIR

# Default checkpoint directory
CHECKPOINT_DIR = DEFAULT_DATA_DIR / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# Default: checkpoint every N turns
AUTO_CHECKPOINT_INTERVAL = 5


def _checkpoint_path(name: str) -> Path:
    """Get full path for a checkpoint by name."""
    return CHECKPOINT_DIR / f"{name}.json"


def _list_checkpoints() -> list[dict]:
    """List all saved checkpoints sorted by creation time (newest first)."""
    if not CHECKPOINT_DIR.exists():
        return []
    checkpoints = []
    for f in sorted(CHECKPOINT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.suffix == ".json":
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                checkpoints.append({
                    "name": f.stem,
                    "created_at": data.get("created_at", ""),
                    "turn": data.get("turn", 0),
                    "size": f.stat().st_size,
                    "type": data.get("type", "auto"),
                })
            except (json.JSONDecodeError, OSError):
                continue
    return checkpoints


class CheckpointManager:
    """Agent durum checkpoint'lerini yönetir.

    Kullanım:
        cm = CheckpointManager()
        await cm.save(state_data, name="my_snapshot", cp_type="manual")
        data = await cm.load("my_snapshot")
        latest = await cm.load_latest()
    """

    def __init__(self, auto_interval: int = AUTO_CHECKPOINT_INTERVAL):
        self.auto_interval = auto_interval
        self._last_auto_turn = 0
        self._current_turn = 0

    @property
    def should_checkpoint(self) -> bool:
        """Check if an auto-checkpoint should be taken based on turn count."""
        if self._current_turn == 0:
            return False
        return (self._current_turn - self._last_auto_turn) >= self.auto_interval

    async def save(
        self,
        state_data: dict[str, Any],
        name: Optional[str] = None,
        cp_type: str = "auto",
    ) -> str:
        """Save a checkpoint.

        Args:
            state_data: Full state dict to snapshot (context, turn, messages, etc.)
            name: Checkpoint name (auto-generated if None)
            cp_type: 'auto' for automatic, 'manual' for user-requested snapshots

        Returns:
            Checkpoint name (stem).
        """
        if name is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            name = f"checkpoint_{timestamp}"

        # Build checkpoint payload
        checkpoint = {
            "type": cp_type,
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "turn": state_data.get("turn", 0),
            "state": state_data.get("state", ""),
            "messages": state_data.get("messages", []),
            "metadata": state_data.get("metadata", {}),
            "sm_history": state_data.get("sm_history", []),
        }

        path = _checkpoint_path(name)
        try:
            path.write_text(
                json.dumps(checkpoint, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            if cp_type == "auto":
                self._last_auto_turn = self._current_turn
            log.info(f"Checkpoint saved [{cp_type}]: {name} ({path.stat().st_size} bytes)")
        except OSError as e:
            log.error(f"Checkpoint save failed [{name}]: {e}")
            raise

        # Prune old auto-checkpoints (keep last 20)
        self._prune_old(max_keep=20)

        return name

    async def load(self, name: str) -> Optional[dict[str, Any]]:
        """Load a checkpoint by name.

        Args:
            name: Checkpoint name (stem, without .json)

        Returns:
            Checkpoint data dict or None if not found.
        """
        path = _checkpoint_path(name)
        if not path.exists():
            log.warning(f"Checkpoint not found: {name}")
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            log.info(f"Checkpoint loaded: {name} (turn={data.get('turn', '?')})")
            return data
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"Checkpoint load failed [{name}]: {e}")
            return None

    async def load_latest(self, cp_type: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Load the most recent checkpoint, optionally filtered by type.

        Args:
            cp_type: Filter by 'auto', 'manual', or None for any.

        Returns:
            Latest checkpoint data or None.
        """
        checkpoints = _list_checkpoints()
        if cp_type:
            checkpoints = [c for c in checkpoints if c.get("type") == cp_type]
        if not checkpoints:
            return None
        return await self.load(checkpoints[0]["name"])

    async def delete(self, name: str) -> bool:
        """Delete a checkpoint by name."""
        path = _checkpoint_path(name)
        if path.exists():
            path.unlink()
            log.info(f"Checkpoint deleted: {name}")
            return True
        return False

    async def list(self, cp_type: Optional[str] = None) -> list[dict]:
        """List all checkpoints, optionally filtered by type."""
        checkpoints = _list_checkpoints()
        if cp_type:
            checkpoints = [c for c in checkpoints if c.get("type") == cp_type]
        return checkpoints

    def _prune_old(self, max_keep: int = 20):
        """Remove oldest auto-checkpoints beyond max_keep."""
        checkpoints = _list_checkpoints()
        auto_cps = [c for c in checkpoints if c.get("type") == "auto"]
        if len(auto_cps) <= max_keep:
            return
        to_remove = sorted(auto_cps, key=lambda c: c["created_at"])[:-max_keep]
        for cp in to_remove:
            path = _checkpoint_path(cp["name"])
            try:
                path.unlink()
                log.debug(f"Pruned old checkpoint: {cp['name']}")
            except OSError:
                pass

    def update_turn(self, turn: int):
        """Update internal turn counter (called from agent loop)."""
        self._current_turn = turn

    def reset(self):
        """Reset checkpoint tracking state."""
        self._last_auto_turn = 0
        self._current_turn = 0


# Singleton
checkpoint_manager = CheckpointManager()
