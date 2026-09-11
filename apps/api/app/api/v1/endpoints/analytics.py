"""Analytics endpoints — overview dashboard and recent traces."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Case, CaseStatus, TraceResult
from app.schemas.trace import (
    AnalyticsOverview,
    RecentTrace,
    RecentTracesResponse,
    TopExchange,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/overview")
async def analytics_overview(db: AsyncSession = Depends(get_db)):
    """Dashboard overview: totals, averages, top exchanges, recent traces."""

    # Total traces
    total_q = select(func.count()).select_from(Case)
    total_traces = (await db.execute(total_q)).scalar() or 0

    # Total identified (cases with an attributed entity)
    identified_q = (
        select(func.count())
        .select_from(Case)
        .where(Case.attributed_entity.isnot(None))
    )
    total_identified = (await db.execute(identified_q)).scalar() or 0

    # Average trace time (from created_at to completed_at, in ms)
    avg_time_q = (
        select(
            func.avg(
                func.extract("epoch", Case.completed_at - Case.created_at) * 1000
            )
        )
        .where(Case.completed_at.isnot(None))
    )
    avg_trace_time_ms = (await db.execute(avg_time_q)).scalar()
    avg_trace_time_ms = int(avg_trace_time_ms) if avg_trace_time_ms else 0

    # Top exchanges (most attributed entities)
    top_ex_q = (
        select(Case.attributed_entity, func.count().label("cnt"))
        .where(Case.attributed_entity.isnot(None))
        .group_by(Case.attributed_entity)
        .order_by(desc("cnt"))
        .limit(10)
    )
    top_rows = (await db.execute(top_ex_q)).all()
    top_exchanges = [
        TopExchange(name=row[0], count=row[1]) for row in top_rows
    ]

    # Recent traces (last 5 for overview)
    recent_q = (
        select(Case)
        .order_by(desc(Case.created_at))
        .limit(5)
    )
    recent_rows = (await db.execute(recent_q)).scalars().all()
    recent_traces = [
        {
            "trace_id": str(c.case_id),
            "address": c.reported_address,
            "chain": c.reported_chain.value,
            "status": c.status.value,
            "attributed_entity": c.attributed_entity,
            "risk_score": c.risk_score,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in recent_rows
    ]

    return AnalyticsOverview(
        total_traces=total_traces,
        total_identified=total_identified,
        avg_trace_time_ms=avg_trace_time_ms,
        top_exchanges=top_exchanges,
        recent_traces=recent_traces,
    )


@router.get("/recent")
async def analytics_recent(db: AsyncSession = Depends(get_db)):
    """Last 20 traces with status, address, and attribution result."""
    stmt = (
        select(Case)
        .order_by(desc(Case.created_at))
        .limit(20)
    )
    rows = (await db.execute(stmt)).scalars().all()

    traces = [
        RecentTrace(
            trace_id=str(c.case_id),
            address=c.reported_address,
            chain=c.reported_chain.value,
            status=c.status.value,
            attributed_entity=c.attributed_entity,
            risk_score=c.risk_score,
            created_at=c.created_at,
        )
        for c in rows
    ]

    return RecentTracesResponse(traces=traces)
