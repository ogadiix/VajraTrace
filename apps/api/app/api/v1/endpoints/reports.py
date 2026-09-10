"""Report endpoints — stubs returning 501."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/{trace_id}/pdf")
async def generate_pdf(trace_id: str):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{trace_id}/status")
async def report_status(trace_id: str):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{trace_id}/download")
async def download_report(trace_id: str):
    raise HTTPException(status_code=501, detail="Not implemented")
