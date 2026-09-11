"""Report endpoints — PDF generation and download.

Exposes two endpoints:
  - ``POST /api/v1/reports/{trace_id}/pdf`` — generate a professional PDF report
  - ``GET  /api/v1/reports/{report_id}/download`` — serve the generated PDF file

The actual report rendering is delegated to
:func:`app.services.reports.generator.generate_report`.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Case, CaseStatus
from app.services.reports.generator import generate_report

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory store for generated reports (swap to a DB table for prod)
_reports: Dict[str, Dict[str, Any]] = {}
# report_id -> {"trace_id": str, "path": str, "created_at": datetime}

_REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "/app/data/reports" if Path("/app").exists() else str(Path(__file__).resolve().parents[6] / "data" / "reports")))
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/{trace_id}/pdf")
async def generate_pdf(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generate a professional PDF investigation report for a completed trace.

    The endpoint validates that the trace exists and is in ``COMPLETED`` state,
    then delegates to the WeasyPrint-based report generator. The resulting PDF
    is saved to disk and a download URL is returned.
    """
    # Validate the trace exists
    case = await db.get(Case, UUID(trace_id))
    if case is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    if case.status != CaseStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Trace not yet completed (status: {case.status.value}). Cannot generate report.",
        )

    # Generate the PDF
    try:
        pdf_bytes, report_id, evidence_hash = await generate_report(trace_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("PDF generation failed for trace %s", trace_id)
        raise HTTPException(
            status_code=500,
            detail="Report generation failed. Please try again.",
        )

    # Track the report
    report_path = _REPORTS_DIR / f"{report_id}.pdf"
    _reports[report_id] = {
        "trace_id": trace_id,
        "path": str(report_path),
        "created_at": datetime.now(timezone.utc),
    }

    logger.info("Generated PDF report %s for trace %s", report_id, trace_id)

    return {
        "report_id": report_id,
        "download_url": f"/api/v1/reports/{report_id}/download",
        "evidence_hash": evidence_hash,
        "size_bytes": len(pdf_bytes),
    }


@router.get("/{report_id}/download")
async def download_report(report_id: str):
    """Download a generated PDF investigation report.

    Returns the PDF file with appropriate headers for browser display
    or download.
    """
    report = _reports.get(report_id)

    # Fallback: check disk even if not in memory (e.g. after server restart)
    if report is None:
        pdf_path = _REPORTS_DIR / f"{report_id}.pdf"
        json_path = _REPORTS_DIR / f"{report_id}.json"

        if pdf_path.exists():
            report = {"path": str(pdf_path)}
        elif json_path.exists():
            report = {"path": str(json_path)}
        else:
            raise HTTPException(status_code=404, detail="Report not found")

    path = Path(report["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file missing from disk")

    # Determine media type based on extension
    if path.suffix == ".pdf":
        media_type = "application/pdf"
    else:
        media_type = "application/json"

    return FileResponse(
        path=str(path),
        media_type=media_type,
        filename=f"vajratrace_report_{report_id}{path.suffix}",
    )
