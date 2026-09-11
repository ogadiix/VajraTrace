"""PDF Report Generator — WeasyPrint + Jinja2 engine for VajraTrace.

Generates professional, government-ready PDF investigation reports from
completed trace results. Each report includes:

  - Case summary with VASP attribution and risk scoring
  - Agent-generated executive narrative
  - Tamper-evident evidence chain table
  - Fund flow summary with bridge hop details
  - SHAP-explained risk assessment
  - Recommended next actions
  - SHA-256 evidence integrity hash with QR code

Usage::

    pdf_bytes, report_id, evidence_hash = await generate_report(trace_id, db)

Note: WeasyPrint requires system-level libraries (Pango, Cairo).
  - Windows: bundled with the ``weasyprint`` wheel
  - Linux/Docker: ``apt install libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0``
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.models import Case, CaseStatus, EvidenceChain, TraceResult

logger = logging.getLogger(__name__)

# ── Paths ──
_TEMPLATE_DIR = Path(__file__).resolve().parent
_REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "/app/data/reports" if Path("/app").exists() else str(Path(__file__).resolve().parents[5] / "data" / "reports")))
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Jinja2 environment ──
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_evidence_hash(evidence_data: List[Dict[str, Any]]) -> str:
    """Compute SHA-256 hash of the serialized evidence JSON payload.

    The evidence list is serialized with sorted keys and no extra whitespace
    to ensure deterministic hashing regardless of dict ordering.

    Args:
        evidence_data: List of evidence entry dicts.

    Returns:
        Lowercase hex digest of the SHA-256 hash.
    """
    canonical = json.dumps(evidence_data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generate_qr_base64(data: str) -> str:
    """Generate a QR code encoding ``data`` and return it as a base64 data URI.

    Uses the ``qrcode`` library with PIL backend. The QR code is rendered
    as a compact PNG with a white background and teal-ish (#0F172A) modules.

    Args:
        data: The string to encode in the QR code.

    Returns:
        A ``data:image/png;base64,...`` URI string for embedding in HTML.
    """
    import qrcode
    from qrcode.image.pil import PilImage

    qr = qrcode.QRCode(
        version=None,  # auto-size
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img: PilImage = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    b64 = base64.b64encode(buffer.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _risk_level(score: Optional[float]) -> Tuple[str, str]:
    """Map a 0–1 risk score to a human-readable label and CSS class.

    Args:
        score: Risk score in [0, 1], or ``None``.

    Returns:
        Tuple of ``(label, css_class)`` — e.g. ``("Critical", "critical")``.
    """
    if score is None:
        return "Unknown", "medium"
    if score >= 0.75:
        return "Critical", "critical"
    if score >= 0.50:
        return "High", "high"
    if score >= 0.25:
        return "Medium", "medium"
    return "Low", "low"


def _confidence_class(conf: Optional[float]) -> str:
    """Return a CSS class name for a confidence value bar colour.

    Args:
        conf: Confidence in [0, 1], or ``None``.

    Returns:
        One of ``"high"``, ``"medium"``, or ``"low"``.
    """
    if conf is None:
        return "low"
    if conf >= 0.7:
        return "high"
    if conf >= 0.4:
        return "medium"
    return "low"


def _format_action(action_value: str) -> str:
    """Convert an EvidenceActionEnum value to a readable label.

    E.g. ``"FETCH_TX_HISTORY"`` → ``"Fetch Tx History"``.

    Args:
        action_value: The raw enum string.

    Returns:
        Title-cased, underscore-removed label.
    """
    return action_value.replace("_", " ").title()


def _extract_shap_factors(
    shap_explanation: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Extract top SHAP contributing factors for the risk assessment section.

    Expects ``shap_explanation`` to be a dict mapping feature names to
    their SHAP values (floats). Returns the top 6 factors sorted by
    absolute contribution.

    Args:
        shap_explanation: Raw SHAP explanation dict from TraceResult, or ``None``.

    Returns:
        List of dicts with keys ``name``, ``value``, ``pct`` (percentage of max).
    """
    if not shap_explanation:
        return []

    # Handle both flat dict and nested formats
    features: Dict[str, float] = {}
    for key, val in shap_explanation.items():
        if isinstance(val, (int, float)):
            features[key] = abs(float(val))
        elif isinstance(val, dict) and "value" in val:
            features[key] = abs(float(val["value"]))

    if not features:
        return []

    sorted_features = sorted(features.items(), key=lambda x: x[1], reverse=True)[:6]
    max_val = sorted_features[0][1] if sorted_features else 1.0
    if max_val == 0:
        max_val = 1.0

    return [
        {
            "name": name.replace("_", " ").title(),
            "value": f"{val:.3f}",
            "pct": round((val / max_val) * 100),
        }
        for name, val in sorted_features
    ]


def _extract_bridge_hops(
    bridge_hops: Optional[Dict[str, Any]],
    reported_chain: str,
) -> Tuple[int, List[str], List[Dict[str, str]]]:
    """Extract fund flow info from TraceResult.bridge_hops.

    Args:
        bridge_hops: Raw bridge hops dict from TraceResult, or ``None``.
        reported_chain: The primary chain of the investigation.

    Returns:
        Tuple of ``(num_hops, chains_involved, key_addresses)``.
        ``key_addresses`` is a list of dicts with ``address``, ``role``, ``chain``.
    """
    chains = {reported_chain}
    key_addresses: List[Dict[str, str]] = []
    num_hops = 0

    if not bridge_hops:
        return num_hops, list(chains), key_addresses

    if isinstance(bridge_hops, dict):
        hops_list = bridge_hops.get("hops", [])
        if isinstance(hops_list, list):
            num_hops = len(hops_list)
            for hop in hops_list:
                if isinstance(hop, dict):
                    if "chain" in hop:
                        chains.add(str(hop["chain"]))
                    if "source_chain" in hop:
                        chains.add(str(hop["source_chain"]))
                    if "dest_chain" in hop:
                        chains.add(str(hop["dest_chain"]))
                    if "address" in hop:
                        key_addresses.append({
                            "address": str(hop["address"]),
                            "role": str(hop.get("role", "Intermediate")),
                            "chain": str(hop.get("chain", reported_chain)),
                        })

        # Also check for a flat structure
        if "chains" in bridge_hops and isinstance(bridge_hops["chains"], list):
            for c in bridge_hops["chains"]:
                chains.add(str(c))

        if "total_hops" in bridge_hops:
            num_hops = max(num_hops, int(bridge_hops["total_hops"]))

        if "addresses" in bridge_hops and isinstance(bridge_hops["addresses"], list):
            for addr_info in bridge_hops["addresses"]:
                if isinstance(addr_info, dict) and "address" in addr_info:
                    key_addresses.append({
                        "address": str(addr_info["address"]),
                        "role": str(addr_info.get("role", "Participant")),
                        "chain": str(addr_info.get("chain", reported_chain)),
                    })

    return num_hops, list(chains), key_addresses


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


async def generate_report(
    trace_id: str,
    db: AsyncSession,
) -> Tuple[bytes, str, str]:
    """Generate a professional PDF investigation report for a completed trace.

    Loads all case data from Postgres, computes evidence integrity hashes,
    generates a QR code, renders a Jinja2 HTML template, and converts it
    to PDF via WeasyPrint.

    Args:
        trace_id: The UUID (as string) of the ``Case`` to report on.
        db:       An active async database session.

    Returns:
        Tuple of ``(pdf_bytes, report_id, evidence_hash)``.

    Raises:
        ValueError: If the trace is not found or not yet completed.
    """
    case_uuid = uuid.UUID(trace_id)

    # ── 1. Load case ──
    case: Optional[Case] = await db.get(Case, case_uuid)
    if case is None:
        raise ValueError(f"Trace {trace_id} not found")

    if case.status != CaseStatus.COMPLETED:
        raise ValueError(
            f"Trace not yet completed (status: {case.status.value}). "
            "Cannot generate report."
        )

    # ── 2. Load trace result ──
    stmt = select(TraceResult).where(TraceResult.case_id == case.case_id)
    trace_result: Optional[TraceResult] = (
        await db.execute(stmt)
    ).scalar_one_or_none()

    # ── 3. Load evidence chain ──
    ev_stmt = (
        select(EvidenceChain)
        .where(EvidenceChain.case_id == case.case_id)
        .order_by(EvidenceChain.step_number)
    )
    evidence_rows = (await db.execute(ev_stmt)).scalars().all()

    # ── 4. Serialize evidence for hashing ──
    evidence_data: List[Dict[str, Any]] = []
    for row in evidence_rows:
        evidence_data.append({
            "step": row.step_number,
            "action": row.action.value,
            "description": row.description,
            "result_summary": row.result_summary,
            "confidence": row.confidence,
            "integrity_hash": row.integrity_hash,
            "raw_data": row.raw_data,
        })

    evidence_hash = _compute_evidence_hash(evidence_data)

    # ── 5. Generate QR code ──
    qr_data_uri = _generate_qr_base64(evidence_hash)

    # ── 6. Prepare template context ──
    now = datetime.now(timezone.utc)
    report_id = str(uuid.uuid4())
    case_id_str = str(case.case_id)
    case_id_short = case_id_str[:8].upper()
    reported_chain = case.reported_chain.value

    # Risk & VASP
    risk_score = trace_result.risk_score if trace_result else case.risk_score
    risk_label, risk_class = _risk_level(risk_score)
    risk_display = f"{risk_score:.0%}" if risk_score is not None else "N/A"

    attributed_vasp = (
        trace_result.attributed_vasp if trace_result and trace_result.attributed_vasp
        else case.attributed_entity or "Unresolved"
    )
    confidence = trace_result.confidence if trace_result else 0.0
    confidence_pct = round(confidence * 100) if confidence else 0

    typology = (
        trace_result.typology if trace_result and trace_result.typology
        else case.typology or "Under Investigation"
    )

    # Executive summary
    executive_summary = (
        trace_result.agent_narrative
        if trace_result and trace_result.agent_narrative
        else None
    )

    # Evidence chain for template
    evidence_chain_ctx: List[Dict[str, Any]] = []
    for entry in evidence_data:
        conf = entry.get("confidence")
        conf_pct = round(conf * 100) if conf is not None else None
        evidence_chain_ctx.append({
            "step": entry["step"],
            "action": _format_action(entry["action"]),
            "finding": entry.get("description", ""),
            "confidence": conf,
            "conf_pct": conf_pct,
            "conf_class": _confidence_class(conf),
        })

    # Fund flow
    bridge_hops_data = trace_result.bridge_hops if trace_result else None
    num_hops, chains_involved, key_addresses = _extract_bridge_hops(
        bridge_hops_data, reported_chain,
    )
    # Fallback: count evidence TX hops
    if num_hops == 0:
        num_hops = sum(
            1 for e in evidence_data if e["action"] == "FETCH_TX_HISTORY"
        )

    # Total value: try to extract from bridge hops, else show "—"
    total_value = "—"
    if bridge_hops_data and isinstance(bridge_hops_data, dict):
        tv = bridge_hops_data.get("total_value") or bridge_hops_data.get("total_value_moved")
        if tv is not None:
            total_value = str(tv)

    # SHAP factors
    shap_explanation = trace_result.shap_explanation if trace_result else None
    shap_factors = _extract_shap_factors(shap_explanation)

    # Sanctions
    sanctions_match = trace_result.sanctions_match if trace_result else False
    sanctions_details = ""
    if trace_result and trace_result.sanctions_details:
        sd = trace_result.sanctions_details
        if isinstance(sd, dict):
            sanctions_details = sd.get("summary", json.dumps(sd, default=str))
        else:
            sanctions_details = str(sd)

    # ── 7. Render template ──
    template = _jinja_env.get_template("template.html")
    html_content = template.render(
        # Header
        case_id=case_id_str,
        case_id_short=case_id_short,
        reported_chain=reported_chain,
        report_date=now.strftime("%d %B %Y"),
        # Section 1: Case Summary
        reported_address=case.reported_address,
        attributed_vasp=attributed_vasp,
        confidence_pct=confidence_pct,
        risk_level=risk_label,
        risk_level_class=risk_class,
        typology=typology,
        # Section 2: Executive Summary
        executive_summary=executive_summary,
        # Section 3: Evidence Chain
        evidence_chain=evidence_chain_ctx,
        # Section 4: Fund Flow
        total_value_traced=total_value,
        num_hops=num_hops,
        chains_involved=chains_involved,
        key_addresses=key_addresses,
        # Section 5: Risk Assessment
        risk_score_display=risk_display,
        shap_factors=shap_factors,
        sanctions_match=sanctions_match,
        sanctions_details=sanctions_details,
        # Section 7: Evidence Integrity
        evidence_hash=evidence_hash,
        qr_code_data_uri=qr_data_uri,
        report_timestamp=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    # ── 8. Convert HTML → PDF ──
    logger.info("Rendering PDF for case %s (report %s)...", case_id_short, report_id)
    pdf_bytes: bytes = HTML(string=html_content).write_pdf()

    # ── 9. Save to disk ──
    report_path = _REPORTS_DIR / f"{report_id}.pdf"
    report_path.write_bytes(pdf_bytes)
    logger.info(
        "Saved report %s (%d bytes) to %s",
        report_id,
        len(pdf_bytes),
        report_path,
    )

    # ── 10. Update case record ──
    case.report_pdf_path = str(report_path)
    case.report_hash = evidence_hash
    await db.commit()

    logger.info(
        "Report generation complete — case=%s report_id=%s hash=%s",
        case_id_short,
        report_id,
        evidence_hash[:16] + "…",
    )

    return pdf_bytes, report_id, evidence_hash
