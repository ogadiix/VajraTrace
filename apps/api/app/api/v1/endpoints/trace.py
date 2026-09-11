"""Trace endpoints — real implementations wired to VajraTrace backend services."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models import (
    Case,
    CaseStatus,
    ChainEnum,
    EvidenceActionEnum,
    EvidenceChain,
    TraceResult as TraceResultModel,
)
from app.schemas.trace import (
    CytoscapeEdge,
    CytoscapeEdgeData,
    CytoscapeNode,
    CytoscapeNodeData,
    EvidenceEntry,
    EvidenceResponse,
    GraphResponse,
    ProgressInfo,
    TraceRequest,
    TraceResponse,
    TraceStatusResponse,
)
from app.services.blockchain.detector import InvalidAddress, detect_chain

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory trace state  (sufficient for single-process; swap to Redis for
# multi-worker deployments)
# ---------------------------------------------------------------------------

_trace_state: Dict[str, Dict[str, Any]] = {}
# trace_id -> {
#   "status": "processing" | "completed" | "failed",
#   "progress": {"step": str, "pct": int},
#   "result": <serialised TraceGraphResult> | None,
#   "graph": {"nodes": [...], "edges": [...]} | None,
#   "started_at": datetime,
#   "completed_at": datetime | None,
#   "error": str | None,
#   "ws_clients": set[WebSocket],
# }

_CHAIN_NAME_TO_ENUM = {
    "bitcoin": ChainEnum.BTC,
    "btc": ChainEnum.BTC,
    "ethereum": ChainEnum.ETH,
    "eth": ChainEnum.ETH,
    "tron": ChainEnum.TRON,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_address(address: str) -> str:
    """Validate and detect the blockchain chain for the address.

    Returns the chain name.  Raises HTTPException 422 on invalid input.
    """
    try:
        return detect_chain(address)
    except InvalidAddress as exc:
        raise HTTPException(status_code=422, detail=f"Invalid address: {exc}") from exc


async def _ws_broadcast(trace_id: str, message: dict) -> None:
    """Send *message* to every connected WebSocket for this trace.

    Dead sockets are silently removed so we never block on a gone client.
    """
    state = _trace_state.get(trace_id)
    if state is None:
        return
    clients: set = state.get("ws_clients", set())
    payload = json.dumps(message, default=str)
    dead: list[WebSocket] = []
    for ws in clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


async def _update_progress(trace_id: str, step: str, pct: int) -> None:
    state = _trace_state.get(trace_id)
    if state:
        state["progress"] = {"step": step, "pct": pct}
    await _ws_broadcast(trace_id, {
        "type": "step",
        "data": {"step": step, "progress": pct},
    })


def _make_evidence_hash(case_id: str, step: int, action: str, prev_hash: str | None) -> str:
    blob = f"{case_id}:{step}:{action}:{prev_hash or 'genesis'}"
    return hashlib.sha256(blob.encode()).hexdigest()


async def _persist_evidence(
    case_id: UUID,
    step: int,
    action: EvidenceActionEnum,
    description: str,
    result_summary: str | None = None,
    confidence: float | None = None,
    raw_data: dict | None = None,
    prev_hash: str | None = None,
) -> str:
    """Insert one evidence-chain row and return its integrity hash."""
    integrity_hash = _make_evidence_hash(str(case_id), step, action.value, prev_hash)
    async with async_session() as session:
        async with session.begin():
            row = EvidenceChain(
                case_id=case_id,
                step_number=step,
                action=action,
                description=description,
                result_summary=result_summary,
                confidence=confidence,
                raw_data=raw_data,
                prev_hash=prev_hash,
                integrity_hash=integrity_hash,
            )
            session.add(row)
    return integrity_hash


async def _set_case_status(case_id: UUID, status: CaseStatus) -> None:
    async with async_session() as session:
        async with session.begin():
            case = await session.get(Case, case_id)
            if case:
                case.status = status
                case.updated_at = datetime.now(timezone.utc)
                if status in (CaseStatus.COMPLETED, CaseStatus.FAILED):
                    case.completed_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Background trace pipeline
# ---------------------------------------------------------------------------


async def _run_trace_pipeline(
    trace_id: str,
    case_id: UUID,
    address: str,
    chain_name: str,
    depth: int,
    include_agent: bool,
) -> None:
    """Execute the full trace pipeline in the background."""
    from app.services.attribution.knowledge_base import knowledge_base
    from app.services.attribution.matcher import VASPMatcher
    from app.services.blockchain.orchestrator import trace_address
    from app.services.clustering.engine import ClusteringEngine
    from app.services.ml.inference import score_address as ml_score_address

    state = _trace_state[trace_id]
    prev_hash: str | None = None
    step_num = 0

    try:
        # ── Step 1: Fetch & trace ─────────────────────────────────────
        await _set_case_status(case_id, CaseStatus.INGESTING)
        await _update_progress(trace_id, "Fetching transactions", 10)

        async with async_session() as db:
            trace_result = await trace_address(address, db, depth=depth)

        step_num += 1
        prev_hash = await _persist_evidence(
            case_id, step_num, EvidenceActionEnum.FETCH_TX_HISTORY,
            f"Traced {address} on {chain_name} to depth {depth}",
            f"{len(trace_result.nodes)} nodes, {len(trace_result.edges)} edges",
            confidence=1.0, prev_hash=prev_hash,
        )

        # Broadcast discovered nodes & edges
        for node in trace_result.nodes:
            await _ws_broadcast(trace_id, {
                "type": "node",
                "data": {
                    "address": node.address,
                    "chain": node.chain,
                    "label": node.label,
                },
            })
        for edge in trace_result.edges:
            await _ws_broadcast(trace_id, {
                "type": "edge",
                "data": {
                    "from": edge.from_address,
                    "to": edge.to_address,
                    "value": str(edge.value),
                    "token": edge.token,
                },
            })

        # ── Step 2: Clustering ────────────────────────────────────────
        await _set_case_status(case_id, CaseStatus.CLUSTERING)
        await _update_progress(trace_id, "Clustering addresses", 30)

        clustering_engine = ClusteringEngine()
        clustering_result = await clustering_engine.run(trace_result)

        step_num += 1
        prev_hash = await _persist_evidence(
            case_id, step_num, EvidenceActionEnum.CLUSTER_ADDRESS,
            f"Clustered {clustering_result.total_addresses_clustered} addresses into {len(clustering_result.clusters)} clusters",
            f"Heuristics: {', '.join(clustering_result.heuristics_applied)}",
            confidence=0.85, prev_hash=prev_hash,
        )

        # ── Step 3: Attribution ───────────────────────────────────────
        await _set_case_status(case_id, CaseStatus.ATTRIBUTING)
        await _update_progress(trace_id, "Attributing entities", 50)

        if not knowledge_base.is_loaded:
            try:
                knowledge_base.load()
            except Exception:
                logger.warning("KnowledgeBase failed to load; attribution will be limited.")

        matcher = VASPMatcher(knowledge_base)
        attribution_result = await matcher.attribute(trace_result, clustering_result)

        step_num += 1
        prev_hash = await _persist_evidence(
            case_id, step_num, EvidenceActionEnum.TAG_LOOKUP,
            f"Attribution: {attribution_result.total_attributed} attributed, {attribution_result.total_unresolved} unresolved",
            attribution_result.highest_confidence_match.entity_name if attribution_result.highest_confidence_match else None,
            confidence=attribution_result.highest_confidence_match.confidence if attribution_result.highest_confidence_match else 0.0,
            prev_hash=prev_hash,
        )

        # Broadcast attribution if we have a high-confidence match
        if attribution_result.highest_confidence_match and attribution_result.highest_confidence_match.entity_name:
            await _ws_broadcast(trace_id, {
                "type": "attribution",
                "data": {
                    "vasp_name": attribution_result.highest_confidence_match.entity_name,
                    "confidence": attribution_result.highest_confidence_match.confidence,
                },
            })

        # ── Step 4: ML Risk Scoring ───────────────────────────────────
        await _set_case_status(case_id, CaseStatus.SCORING)
        await _update_progress(trace_id, "Scoring risk", 70)

        risk_scores: Dict[str, Any] = {}
        for node in trace_result.nodes:
            features = {
                "in_txs_degree": node.tx_count // 2,
                "out_txs_degree": node.tx_count // 2,
                "total_BTC": float(node.total_received + node.total_sent),
                "fees": 0.0,
                "num_input_addresses": node.tx_count // 3,
                "num_output_addresses": node.tx_count // 3,
            }
            result = ml_score_address(features)
            risk_scores[node.address] = {
                "risk_score": result.risk_score,
                "risk_level": result.risk_level,
                "top_factors": result.top_factors,
            }
            node.risk_score = result.risk_score / 100.0

        step_num += 1
        prev_hash = await _persist_evidence(
            case_id, step_num, EvidenceActionEnum.RISK_SCORE,
            f"Scored {len(risk_scores)} addresses with ML risk pipeline",
            json.dumps({k: v["risk_score"] for k, v in list(risk_scores.items())[:10]}, default=str),
            confidence=0.9, prev_hash=prev_hash,
        )

        # ── Step 5: Agent Investigation (optional) ────────────────────
        agent_narrative: str | None = None
        if include_agent:
            await _set_case_status(case_id, CaseStatus.NARRATING)
            await _update_progress(trace_id, "Agent investigation", 85)

            try:
                from app.services.agent.investigator import investigate
                investigation = await investigate(address, chain_name)
                agent_narrative = investigation.summary

                step_num += 1
                prev_hash = await _persist_evidence(
                    case_id, step_num, EvidenceActionEnum.AGENT_NARRATION,
                    "AI agent narration completed",
                    agent_narrative[:500] if agent_narrative else None,
                    confidence=0.7, prev_hash=prev_hash,
                )
            except Exception as exc:
                logger.warning("Agent investigation failed (non-fatal): %s", exc)

        # ── Persist TraceResult to Postgres ───────────────────────────
        best_match = attribution_result.highest_confidence_match
        avg_risk = (
            sum(v["risk_score"] for v in risk_scores.values()) / max(len(risk_scores), 1)
        ) / 100.0

        async with async_session() as session:
            async with session.begin():
                tr = TraceResultModel(
                    case_id=case_id,
                    attributed_vasp=best_match.entity_name if best_match else None,
                    confidence=best_match.confidence if best_match else 0.0,
                    risk_score=min(max(avg_risk, 0.0), 1.0),
                    typology=best_match.match_method if best_match else None,
                    sanctions_match=any(m.is_sanctioned for m in attribution_result.matches),
                    agent_narrative=agent_narrative,
                )
                session.add(tr)

                # Update the Case row
                case = await session.get(Case, case_id)
                if case:
                    case.status = CaseStatus.COMPLETED
                    case.risk_score = min(max(avg_risk, 0.0), 1.0)
                    case.attributed_entity = best_match.entity_name if best_match else None
                    case.completed_at = datetime.now(timezone.utc)
                    case.updated_at = datetime.now(timezone.utc)

        # ── Build Cytoscape graph for fast retrieval ──────────────────
        cyto_nodes = []
        for node in trace_result.nodes:
            attr_match = attribution_result.address_to_match.get(node.address)
            cyto_nodes.append({
                "data": {
                    "id": node.address,
                    "label": (attr_match.entity_name if attr_match and attr_match.entity_name else node.label) or node.address[:12] + "…",
                    "chain": node.chain,
                    "risk_score": node.risk_score,
                    "entity_label": attr_match.entity_name if attr_match else None,
                    "total_received": str(node.total_received),
                    "total_sent": str(node.total_sent),
                    "tx_count": node.tx_count,
                    "first_seen": node.first_seen.isoformat() if node.first_seen else None,
                    "last_seen": node.last_seen.isoformat() if node.last_seen else None,
                }
            })

        cyto_edges = []
        for i, edge in enumerate(trace_result.edges):
            cyto_edges.append({
                "data": {
                    "id": f"e{i}_{edge.tx_hash[:8]}",
                    "source": edge.from_address,
                    "target": edge.to_address,
                    "value": str(edge.value),
                    "token": edge.token,
                    "timestamp": edge.timestamp.isoformat(),
                    "chain": edge.chain,
                    "tx_hash": edge.tx_hash,
                    "block_number": edge.block_number,
                }
            })

        # ── Finalise state ────────────────────────────────────────────
        state["status"] = "completed"
        state["completed_at"] = datetime.now(timezone.utc)
        state["progress"] = {"step": "Completed", "pct": 100}
        state["graph"] = {"nodes": cyto_nodes, "edges": cyto_edges}
        state["result"] = {
            "source_address": trace_result.source_address,
            "chain": trace_result.chain,
            "depth_reached": trace_result.depth_reached,
            "node_count": len(trace_result.nodes),
            "edge_count": len(trace_result.edges),
            "chains_involved": trace_result.chains_involved,
            "total_value_moved": str(trace_result.total_value_moved),
            "stale_data": trace_result.stale_data,
            "trace_duration_ms": trace_result.trace_duration_ms,
            "attribution": {
                "entity_name": best_match.entity_name if best_match else None,
                "confidence": best_match.confidence if best_match else 0.0,
            },
            "risk_score": avg_risk,
            "agent_narrative": agent_narrative,
        }

        await _ws_broadcast(trace_id, {
            "type": "completed",
            "data": state["result"],
        })

        logger.info("Trace pipeline completed for %s (case=%s)", address, case_id)

    except Exception as exc:
        logger.exception("Trace pipeline failed for %s: %s", address, exc)
        state["status"] = "failed"
        state["error"] = str(exc)
        state["completed_at"] = datetime.now(timezone.utc)
        state["progress"] = {"step": "Failed", "pct": 0}

        await _set_case_status(case_id, CaseStatus.FAILED)
        await _ws_broadcast(trace_id, {
            "type": "error",
            "data": {"message": str(exc)},
        })


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/")
async def submit_trace(
    body: TraceRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit a new trace — validates, creates a case, kicks off the pipeline."""
    # Validate address format
    chain_name = _validate_address(body.address)

    # Map chain enum
    chain_enum = _CHAIN_NAME_TO_ENUM.get(chain_name)
    if chain_enum is None:
        raise HTTPException(status_code=422, detail=f"Unsupported chain: {chain_name}")

    # Create Case in Postgres
    case = Case(
        reported_address=body.address,
        reported_chain=chain_enum,
        submitted_by=body.submitted_by,
        investigator_notes=body.notes,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)

    trace_id = str(case.case_id)
    now = datetime.now(timezone.utc)

    # Initialise in-memory state
    _trace_state[trace_id] = {
        "status": "processing",
        "progress": {"step": "Submitted", "pct": 0},
        "result": None,
        "graph": None,
        "started_at": now,
        "completed_at": None,
        "error": None,
        "ws_clients": set(),
    }

    # Fire-and-forget background task
    asyncio.create_task(
        _run_trace_pipeline(
            trace_id=trace_id,
            case_id=case.case_id,
            address=body.address,
            chain_name=chain_name,
            depth=body.depth,
            include_agent=body.include_agent_narrative,
        )
    )

    return TraceResponse(
        trace_id=case.case_id,
        status="processing",
        submitted_at=now,
        ws_url=f"/api/v1/trace/{trace_id}/live",
    )


@router.get("/{trace_id}")
async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Return trace status, progress, and result (if completed)."""
    state = _trace_state.get(trace_id)

    if state:
        started = state["started_at"]
        completed = state.get("completed_at")
        elapsed = (
            (completed - started).total_seconds()
            if completed
            else (datetime.now(timezone.utc) - started).total_seconds()
        )
        return TraceStatusResponse(
            trace_id=UUID(trace_id),
            status=state["status"],
            progress=ProgressInfo(**state["progress"]) if state["progress"] else None,
            result=state.get("result"),
            started_at=started,
            completed_at=completed,
            elapsed_seconds=round(elapsed, 2),
        )

    # Fallback: look up in Postgres
    case = await db.get(Case, UUID(trace_id))
    if case is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    status_map = {
        CaseStatus.COMPLETED: "completed",
        CaseStatus.FAILED: "failed",
    }
    status = status_map.get(case.status, "processing")

    return TraceStatusResponse(
        trace_id=case.case_id,
        status=status,
        progress=None,
        result=None,
        started_at=case.created_at,
        completed_at=case.completed_at,
        elapsed_seconds=(
            (case.completed_at - case.created_at).total_seconds()
            if case.completed_at
            else None
        ),
    )


@router.get("/{trace_id}/graph")
async def get_trace_graph(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Return the graph in Cytoscape.js format."""
    state = _trace_state.get(trace_id)

    if state and state.get("graph"):
        return state["graph"]

    if state and state["status"] == "processing":
        raise HTTPException(status_code=202, detail="Trace still processing")

    # Check if case exists
    case = await db.get(Case, UUID(trace_id))
    if case is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    if case.status != CaseStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail=f"Trace status: {case.status.value}",
        )

    # Graph data was lost (server restarted) — return empty
    return {"nodes": [], "edges": []}


@router.get("/{trace_id}/evidence")
async def get_trace_evidence(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Return the evidence chain from Postgres."""
    case = await db.get(Case, UUID(trace_id))
    if case is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    stmt = (
        select(EvidenceChain)
        .where(EvidenceChain.case_id == case.case_id)
        .order_by(EvidenceChain.step_number)
    )
    rows = (await db.execute(stmt)).scalars().all()

    evidence = [
        EvidenceEntry(
            id=str(row.id),
            step_number=row.step_number,
            action=row.action.value,
            description=row.description,
            result_summary=row.result_summary,
            confidence=row.confidence,
            raw_data=row.raw_data,
            integrity_hash=row.integrity_hash,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return EvidenceResponse(trace_id=trace_id, evidence=evidence)


@router.websocket("/{trace_id}/live")
async def trace_live(websocket: WebSocket, trace_id: str):
    """WebSocket endpoint for real-time trace updates.

    Client connects when trace starts; server pushes JSON messages as
    the pipeline progresses.  Handles disconnects gracefully.
    """
    await websocket.accept()

    state = _trace_state.get(trace_id)
    if state is None:
        await websocket.send_json({"type": "error", "data": {"message": "Trace not found"}})
        await websocket.close(code=4004)
        return

    # Register this client
    state.setdefault("ws_clients", set()).add(websocket)

    # If already completed, send the result immediately
    if state["status"] in ("completed", "failed"):
        msg_type = "completed" if state["status"] == "completed" else "error"
        payload = state.get("result") or {"message": state.get("error", "Unknown error")}
        await websocket.send_json({"type": msg_type, "data": payload})
        state["ws_clients"].discard(websocket)
        await websocket.close()
        return

    # Keep the connection open until trace completes or client disconnects
    try:
        while True:
            # Wait for a message from the client (ping / close)
            # We use a receive with timeout to periodically check status
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a heartbeat
                try:
                    await websocket.send_json({"type": "ping", "data": {}})
                except Exception:
                    break

            # Check if trace completed
            current = _trace_state.get(trace_id, {})
            if current.get("status") in ("completed", "failed"):
                break

    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected for trace %s", trace_id)
    except Exception as exc:
        logger.warning("WebSocket error for trace %s: %s", trace_id, exc)
    finally:
        state = _trace_state.get(trace_id)
        if state:
            state.get("ws_clients", set()).discard(websocket)
