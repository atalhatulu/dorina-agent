"""Pydantic models for the Gateway API."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ChatCompletionRequest(BaseModel):
    """Incoming chat completion request."""
    messages: list[dict[str, Any]] = Field(..., description="Conversation messages")
    stream: bool = Field(default=True, description="Whether to stream the response")
    model: str | None = Field(default=None, description="Model override (optional)")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128_000)


class ToolInfo(BaseModel):
    """Tool metadata exposed via API."""
    name: str
    description: str
    toolset: str
    parameters: dict[str, Any] | None = None


class SessionInfo(BaseModel):
    """Session metadata for API responses."""
    id: str
    title: str
    message_count: int
    summary: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SessionListResponse(BaseModel):
    """List of sessions."""
    sessions: list[SessionInfo]
    total: int
