"""Aggregate v1 API routes."""

from fastapi import APIRouter

from app.api.v1.endpoints import trace, reports, analytics

v1_router = APIRouter(tags=["v1"])

v1_router.include_router(trace.router, prefix="/trace", tags=["trace"])
v1_router.include_router(reports.router, prefix="/reports", tags=["reports"])
v1_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
