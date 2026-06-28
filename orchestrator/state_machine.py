"""
State Machine — agent durum makinesi + checkpoint/snapshot destegi.

LangGraph'in StateGraph deseninden esinlenilmistir.
Agent'in hangi durumda oldugunu, hangi gecislerin mumkun oldugunu yonetir.
Checkpoint/Snapshot: her N adimda otomatik checkpoint, manuel snapshot komutu.

Durumlar:
  IDLE -> THINKING -> (TOOL_CALLING -> WAITING_RESULT) -> SYNTHESIZE -> DONE
                    -> DIRECT_REPLY -> DONE
  THINKING -> THINKING (planning_only retry)
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Callable, Optional
from dataclasses import dataclass, field

from core.logger import log

# P2-13: Checkpoint/Snapshot import
from orchestrator.checkpoint import checkpoint_manager


class AgentState(Enum):
    """Agent durumları."""
    IDLE = "idle"
    THINKING = "thinking"      # LLM düşünüyor
    TOOL_CALLING = "tool"      # Tool çağırıyor
    WAITING_RESULT = "result"  # Tool sonucu bekliyor
    SYNTHESIZE = "synthesize"  # Sonuçları birleştiriyor
    DIRECT_REPLY = "reply"     # Doğrudan cevap veriyor
    DONE = "done"              # Tamamlandı
    ERROR = "error"            # Hata
    FALLBACK = "fallback"      # Alternatif strateji / provider deneme


@dataclass
class StateTransition:
    """Durum geçişi."""
    from_state: AgentState
    to_state: AgentState
    condition: str = ""
    action: Optional[str] = None

@dataclass
class AgentContext:
    """Agent durum makinesinin bağlamı (LangGraph State benzeri)."""

    state: AgentState = AgentState.IDLE
    user_input: str = ""
    llm_response: dict = field(default_factory=dict)
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    final_response: str = ""
    error: Optional[str] = None
    turn: int = 0
    iteration_budget: int = 15
    iterations_used: int = 0
    metadata: dict = field(default_factory=dict)

    def reset(self):
        """Yeni tur için sıfırla."""
        self.state = AgentState.IDLE
        self.user_input = ""
        self.llm_response = {}
        self.tool_calls = []
        self.tool_results = []
        self.final_response = ""
        self.error = None
        self.turn = 0
        self.metadata = {}


class StateMachine:
    """
    Agent durum makinesi.
    
    Kullanım:
        sm = StateMachine()
        sm.add_transition(AgentState.IDLE, AgentState.THINKING, "start")
        sm.add_transition(AgentState.THINKING, AgentState.TOOL_CALLING, "has_tools")
        result = await sm.run(context, handlers)
    """

    def __init__(self):
        self.transitions: dict[AgentState, list[StateTransition]] = {
            AgentState.IDLE: [],
            AgentState.THINKING: [],
            AgentState.TOOL_CALLING: [],
            AgentState.WAITING_RESULT: [],
            AgentState.SYNTHESIZE: [],
            AgentState.DIRECT_REPLY: [],
            AgentState.DONE: [],
            AgentState.ERROR: [],
            AgentState.FALLBACK: [],
        }
        self.history: list[AgentState] = []

    def add_transition(self, from_state: AgentState, to_state: AgentState,
                       condition: str = "", action: str = None):
        """Durum geçişi ekle."""
        self.transitions[from_state].append(
            StateTransition(from_state, to_state, condition, action)
        )

    def _evaluate_condition(self, condition: str, context: AgentContext) -> bool:
        """Koşul string'ini context'e göre değerlendir."""
        if not condition:
            return True

        conditions = {
            "start": lambda: True,
            "has_tools": lambda: context.metadata.get('has_tools', False),
            "no_tools": lambda: not context.metadata.get('has_tools', True) and not context.metadata.get('planning_retry', False),
            "planning_only": lambda: context.metadata.get('planning_retry', False),
            "wait": lambda: True,
            "more_tools": lambda: context.metadata.get('more_tools', False),
            "enough": lambda: not context.metadata.get('more_tools', True),
            "loop": lambda: context.metadata.get('more_tools', False),
            "truncated": lambda: context.metadata.get('truncated', False),
            "finalized": lambda: context.metadata.get('finalized', False),
            "error": lambda: context.metadata.get('has_error', False),
            "all_failed": lambda: context.metadata.get('all_tools_failed', False),
            "done": lambda: True,
            "unknown": lambda: True,
        }
        evaluator = conditions.get(condition)
        if evaluator:
            return evaluator()
        return True

    def _get_next_state(self, context: AgentContext) -> tuple[AgentState, Optional[str]]:
        """Sıradaki durumu belirle — koşulları değerlendirerek."""
        current = context.state
        possible = self.transitions.get(current, [])

        if possible:
            for t in possible:
                if self._evaluate_condition(t.condition, context):
                    return t.to_state, t.condition

        # Default transitions (fallback)
        defaults = {
            AgentState.IDLE: (AgentState.THINKING, "start"),
            AgentState.THINKING: (AgentState.DIRECT_REPLY, "no_tools"),
            AgentState.TOOL_CALLING: (AgentState.WAITING_RESULT, "wait"),
            AgentState.WAITING_RESULT: (AgentState.THINKING, "loop"),
            AgentState.DIRECT_REPLY: (AgentState.DONE, "done"),
            AgentState.SYNTHESIZE: (AgentState.DONE, "done"),
            AgentState.ERROR: (AgentState.FALLBACK, "fallback"),
            AgentState.FALLBACK: (AgentState.THINKING, "start"),
        }
        return defaults.get(current, (AgentState.DONE, "unknown"))

    async def run(self, context: AgentContext, handlers: dict[str, Callable]) -> str:
        """Durum makinesini çalıştır."""
        self.history = []
        max_transitions = 100  # Circuit breaker: prevent infinite loops (50 was insufficient for multi-step tasks)
        transitions = 0

        while context.state != AgentState.DONE:
            # Circuit breaker
            transitions += 1
            if transitions > max_transitions:
                log.error(f"Circuit breaker triggered after {max_transitions} transitions")
                context.state = AgentState.DONE
                context.error = "Circuit breaker: too many state transitions"
                break

            self.history.append(context.state)
            handler = handlers.get(context.state.value)

            if handler:
                try:
                    await handler(context)
                except Exception as e:
                    context.state = AgentState.ERROR
                    context.error = str(e)
                    from rich.markup import escape as _esc
                    log.error("State handler hatasi [%s]: %s", _esc(str(context.state)), _esc(str(e)))
                    # Doğrudan ERROR state'i için next_state'i hesapla
                    pass

            # Hata oluştuğunda sonsuz döngüyü önlemek için
            if context.state == AgentState.ERROR and not self.transitions.get(AgentState.ERROR):
                break

            # Find next state
            next_state, condition = self._get_next_state(context)
            log.debug(f"State: {context.state.value} → {next_state.value} ({condition})")
            context.state = next_state

            # Eğer ERROR handler'dan dönen next_state yine ERROR veya DONE ise devam et
            if context.state == AgentState.ERROR and condition == "unknown":
                 break

        if context.state == AgentState.ERROR or context.error:
            return f"Hata: {context.error}"

        return context.final_response

    def reset_history(self, context: Optional[AgentContext] = None):
        """State geçmişini sıfırla, opsiyonel olarak AgentContext'i de sıfırla."""
        self.history = []
        if context:
            context.reset()

    # ── P2-13: Checkpoint/Snapshot ──────────────────────────────

    def get_state_data(self, context: AgentContext, extra_messages: Optional[list] = None) -> dict:
        """Collect full state data for checkpointing."""
        return {
            "turn": context.turn,
            "state": context.state.value if context.state else "",
            "messages": extra_messages or [],
            "metadata": context.metadata,
            "sm_history": self.history,
        }

    def restore_from_checkpoint(self, data: dict, context: AgentContext):
        """Restore agent state from checkpoint data."""
        turn = data.get("turn", 0)
        context.turn = turn
        context.metadata = data.get("metadata", {})

        # Restore state enum
        state_str = data.get("state", "idle")
        for st in AgentState:
            if st.value == state_str:
                context.state = st
                break
        else:
            context.state = AgentState.IDLE

        # Restore saved history
        self.history = data.get("sm_history", [])

        log.info(
            f"State restored from checkpoint: turn={turn}, "
            f"state={context.state.value}"
        )

    async def auto_checkpoint(self, context: AgentContext) -> Optional[str]:
        """Auto-save checkpoint if enough turns have passed.

        Returns checkpoint name if saved, None otherwise.
        """
        checkpoint_manager.update_turn(context.turn)
        if checkpoint_manager.should_checkpoint:
            name = await checkpoint_manager.save(
                self.get_state_data(context),
                cp_type="auto",
            )
            return name
        return None

    async def snapshot(self, context: AgentContext, name: Optional[str] = None) -> str:
        """Manual snapshot (user-requested).

        Args:
            context: Current agent context
            name: Optional custom name for the snapshot

        Returns:
            Snapshot name.
        """
        return await checkpoint_manager.save(
            self.get_state_data(context),
            name=name,
            cp_type="manual",
        )

    async def list_checkpoints(self) -> list[dict]:
        """List all saved checkpoints."""
        return await checkpoint_manager.list()


# Default state machine configuration
def create_default_machine() -> StateMachine:
    """Varsayılan agent durum makinesini oluştur."""
    sm = StateMachine()

    sm.add_transition(AgentState.IDLE, AgentState.THINKING, "start")
    sm.add_transition(AgentState.THINKING, AgentState.THINKING, "planning_only")
    sm.add_transition(AgentState.THINKING, AgentState.TOOL_CALLING, "has_tools")
    sm.add_transition(AgentState.THINKING, AgentState.DIRECT_REPLY, "no_tools")
    sm.add_transition(AgentState.THINKING, AgentState.DIRECT_REPLY, "finalized")
    sm.add_transition(AgentState.THINKING, AgentState.ERROR, "error")
    sm.add_transition(AgentState.TOOL_CALLING, AgentState.WAITING_RESULT, "wait")
    sm.add_transition(AgentState.TOOL_CALLING, AgentState.ERROR, "error")
    sm.add_transition(AgentState.WAITING_RESULT, AgentState.THINKING, "more_tools")
    sm.add_transition(AgentState.WAITING_RESULT, AgentState.SYNTHESIZE, "enough")
    sm.add_transition(AgentState.WAITING_RESULT, AgentState.ERROR, "error")
    sm.add_transition(AgentState.DIRECT_REPLY, AgentState.DONE, "done")
    sm.add_transition(AgentState.SYNTHESIZE, AgentState.DONE, "done")
    sm.add_transition(AgentState.SYNTHESIZE, AgentState.ERROR, "error")
    sm.add_transition(AgentState.ERROR, AgentState.FALLBACK, "fallback")
    sm.add_transition(AgentState.FALLBACK, AgentState.THINKING, "start")
    sm.add_transition(AgentState.FALLBACK, AgentState.DONE, "abort")

    return sm
