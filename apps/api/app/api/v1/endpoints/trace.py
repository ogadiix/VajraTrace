"""Trace endpoints — stubs returning 501."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/")
async def submit_trace():
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{trace_id}")
async def get_trace(trace_id: str):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{trace_id}/graph")
async def get_trace_graph(trace_id: str):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{trace_id}/evidence")
async def get_trace_evidence(trace_id: str):
    raise HTTPException(status_code=501, detail="Not implemented")
