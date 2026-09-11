"""Pydantic request/response schemas for all VajraTrace API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import ChainEnum


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------


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


class ProgressInfo(BaseModel):
    step: str = ""
    pct: int = 0


class TraceStatusResponse(BaseModel):
    trace_id: UUID
    status: str
    progress: Optional[ProgressInfo] = None
    result: Optional[Dict[str, Any]] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    elapsed_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Graph (Cytoscape.js format)
# ---------------------------------------------------------------------------


class CytoscapeNodeData(BaseModel):
    id: str
    label: Optional[str] = None
    chain: Optional[str] = None
    risk_score: Optional[float] = None
    entity_label: Optional[str] = None
    total_received: Optional[str] = None
    total_sent: Optional[str] = None
    tx_count: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


class CytoscapeNode(BaseModel):
    data: CytoscapeNodeData


class CytoscapeEdgeData(BaseModel):
    id: str
    source: str
    target: str
    value: str
    token: str
    timestamp: Optional[str] = None
    chain: Optional[str] = None
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None


class CytoscapeEdge(BaseModel):
    data: CytoscapeEdgeData


class GraphResponse(BaseModel):
    nodes: List[CytoscapeNode]
    edges: List[CytoscapeEdge]


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class EvidenceEntry(BaseModel):
    id: str
    step_number: int
    action: str
    description: str
    result_summary: Optional[str] = None
    confidence: Optional[float] = None
    raw_data: Optional[Dict[str, Any]] = None
    integrity_hash: str
    created_at: datetime


class EvidenceResponse(BaseModel):
    trace_id: str
    evidence: List[EvidenceEntry]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class ReportGenerateResponse(BaseModel):
    report_id: str
    download_url: str


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class TopExchange(BaseModel):
    name: str
    count: int


class AnalyticsOverview(BaseModel):
    total_traces: int
    total_identified: int
    avg_trace_time_ms: int
    top_exchanges: List[TopExchange]
    recent_traces: List[Dict[str, Any]]


class RecentTrace(BaseModel):
    trace_id: str
    address: str
    chain: str
    status: str
    attributed_entity: Optional[str] = None
    risk_score: Optional[float] = None
    created_at: datetime


class RecentTracesResponse(BaseModel):
    traces: List[RecentTrace]
