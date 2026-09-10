"""Pydantic request/response schemas for trace endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import ChainEnum


class TraceRequest(BaseModel):
    address: str = Field(..., max_length=128)
    chain: ChainEnum
    depth: int = Field(default=3, ge=1, le=6)
    include_agent_narrative: bool = False
    submitted_by: Optional[str] = None
    notes: Optional[str] = None


class TraceResponse(BaseModel):
    trace_id: UUID
    status: str
    submitted_at: datetime
    estimated_duration_seconds: int = 45
    ws_url: str


class TraceStatusResponse(BaseModel):
    trace_id: UUID
    status: str
    progress: Optional[dict] = None
    result: Optional[dict] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    elapsed_seconds: Optional[float] = None
