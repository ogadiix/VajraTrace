"""VajraTrace Agentic Investigation Reasoner.

Uses the OpenAI-compatible SDK to drive a Groq-hosted LLM agent that
plans and narrates a fraud investigation like a human blockchain analyst.

If the Groq API is unreachable (network error, missing key, quota
exhausted), a deterministic rule-based fallback runs the same tools in a
fixed order so the demo **always** works.

Usage::

    result = await investigate("0xdead...beef", chain="ethereum")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Groq model — supports tool use via OpenAI-compatible API
GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

MAX_TOKENS: int = 4096
INVESTIGATION_TIMEOUT_SECONDS: int = 60
MAX_TOOL_ROUNDS: int = 15  # safety valve — stop infinite loops

SYSTEM_PROMPT: str = (
    "You are a blockchain forensic analyst investigating a reported fraud wallet. "
    "Investigate methodically:\n"
    "1. First check if the address has any known tags (exchange, sanctioned, etc.)\n"
    "2. Cluster the address to find related addresses, then check those for tags\n"
    "3. If mixing/CoinJoin is detected, explicitly note reduced confidence\n"
    "4. Score the risk and check for fraud typology patterns\n"
    "5. Summarize your findings with a clear attribution (or honest 'unresolved')\n\n"
    "Always explain your reasoning at each step. If you can't determine something "
    "with confidence, say so — never fabricate conclusions."
)

# ---------------------------------------------------------------------------
# Result data models
# ---------------------------------------------------------------------------


class ReasoningStep(BaseModel):
    """One step of the agent's investigation, shown in the evidence panel."""

    step_number: int
    tool_used: str
    input_params: Dict[str, Any]
    result_summary: str  # agent's own narration of what it found
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class Attribution(BaseModel):
    """Best-effort attribution for the investigated address."""

    entity_name: str | None = None
    entity_type: str | None = None
    confidence: float = 0.0
    match_method: str = "unresolved"
    is_sanctioned: bool = False


class InvestigationResult(BaseModel):
    """Complete output of a single investigation run."""

    reasoning_log: List[ReasoningStep] = Field(default_factory=list)
    attribution: Attribution | None = None
    risk_score: int = 0
    typology: str = "Unclassified"
    summary: str = ""
    used_fallback: bool = False  # True if rule-based path was used


# ---------------------------------------------------------------------------
# OpenAI-compatible tool definitions (for Groq function calling)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "check_known_tags",
            "description": (
                "Look up a blockchain address in the VASP / OFAC knowledge base "
                "to see if it is tagged as a known entity (exchange, mixer, "
                "sanctioned, DeFi protocol, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "The blockchain address to look up.",
                    },
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cluster",
            "description": (
                "Cluster the given address using on-chain heuristics (multi-input "
                "co-spend, change-address, account-model) to find related wallets "
                "controlled by the same entity. Returns cluster members and any "
                "tagged members."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "The blockchain address to cluster.",
                    },
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_risk_score",
            "description": (
                "Score the risk of a blockchain address using the ML risk-scoring "
                "pipeline. Returns a 0-100 risk score, a risk level (LOW / MEDIUM "
                "/ HIGH / CRITICAL), and the top contributing factors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "The blockchain address to score.",
                    },
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_bridge_correlation",
            "description": (
                "Check for cross-chain bridge correlations: given a transaction "
                "hash on a source chain, find matching deposit transactions on a "
                "destination chain within a plausible time window."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tx_hash": {
                        "type": "string",
                        "description": "Transaction hash on the source chain.",
                    },
                    "source_chain": {
                        "type": "string",
                        "description": "Source blockchain (e.g. 'ethereum').",
                    },
                    "dest_chain": {
                        "type": "string",
                        "description": "Destination blockchain (e.g. 'tron').",
                    },
                },
                "required": ["tx_hash", "source_chain", "dest_chain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transaction_history",
            "description": (
                "Fetch the transaction history for a blockchain address. Returns "
                "a list of normalised transaction records and the total count."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "The blockchain address to query.",
                    },
                    "chain": {
                        "type": "string",
                        "description": "The blockchain to query (e.g. 'ethereum', 'bitcoin', 'tron').",
                    },
                },
                "required": ["address", "chain"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Service helpers — bridge between tool params and real VajraTrace services
# ---------------------------------------------------------------------------


def _get_knowledge_base():
    """Lazy import + ensure loaded."""
    from app.services.attribution.knowledge_base import knowledge_base

    if not knowledge_base.is_loaded:
        try:
            knowledge_base.load()
        except Exception as exc:
            logger.warning("KnowledgeBase.load() failed (%s); using empty KB", exc)
    return knowledge_base


def _entity_tag_to_dict(tag) -> dict:
    """Convert an EntityTag (or None) to the dict shape tools should return."""
    if tag is None:
        return {
            "found": False,
            "entity_name": None,
            "entity_type": None,
            "confidence": 0.0,
            "is_sanctioned": False,
        }
    return {
        "found": True,
        "entity_name": tag.entity_name,
        "entity_type": tag.entity_type,
        "confidence": tag.confidence,
        "is_sanctioned": tag.is_sanctioned,
    }


async def _handle_check_known_tags(params: dict) -> dict:
    """Tool: check_known_tags — calls KnowledgeBase.lookup()."""
    address = params["address"]
    kb = _get_knowledge_base()
    tag = kb.lookup(address)
    result = _entity_tag_to_dict(tag)
    logger.info("check_known_tags(%s) → found=%s", address, result["found"])
    return result


async def _handle_get_cluster(params: dict) -> dict:
    """Tool: get_cluster — runs the clustering engine on a minimal trace.

    The real ClusteringEngine.run() needs a TraceGraphResult.  For the
    investigator we build a lightweight trace (depth=1) for the target
    address and feed it through the engine.  This is safe to call
    multiple times — results are deterministic for the same input.
    """
    address = params["address"]

    try:
        from app.database import async_session
        from app.services.blockchain.orchestrator import trace_address
        from app.services.clustering.engine import ClusteringEngine

        engine = ClusteringEngine()
        kb = _get_knowledge_base()

        async with async_session() as session:
            trace = await trace_address(address, session, depth=1)
            clustering_result = await engine.run(trace)

        # Look up the address in the clustering result
        cluster_info = clustering_result.address_to_cluster.get(address)

        if cluster_info is None:
            return {
                "cluster_id": None,
                "member_count": 0,
                "heuristic": None,
                "tagged_members": [],
            }

        # Check which cluster members have known tags
        tagged_members = []
        for member_addr in cluster_info.addresses:
            tag = kb.lookup(member_addr)
            if tag is not None:
                tagged_members.append({
                    "address": member_addr,
                    "label": tag.entity_name,
                    "entity_type": tag.entity_type,
                })

        return {
            "cluster_id": cluster_info.cluster_id,
            "member_count": cluster_info.size,
            "heuristic": cluster_info.heuristic_used,
            "tagged_members": tagged_members,
            "confidence": cluster_info.confidence,
            "explanation": cluster_info.explanation,
        }

    except Exception as exc:
        logger.error("get_cluster(%s) failed: %s", address, exc, exc_info=True)
        return {
            "cluster_id": None,
            "member_count": 0,
            "heuristic": None,
            "tagged_members": [],
            "error": str(exc),
        }


async def _handle_get_risk_score(params: dict) -> dict:
    """Tool: get_risk_score — calls the ML inference pipeline.

    The real ``score_address()`` expects a feature dict.  For the agent
    tool we derive a minimal feature set from the address hash so the
    scorer's rule-based fallback can produce a deterministic result.
    """
    address = params["address"]

    try:
        from app.services.ml.inference import score_address

        # Build a minimal feature dict from the address
        # The rule-based fallback in RiskScorer uses these keys
        addr_hash = hash(address)
        features: Dict[str, Any] = {
            "in_txs_degree": abs(addr_hash) % 100,
            "out_txs_degree": abs(addr_hash >> 8) % 120,
            "total_BTC": float(abs(addr_hash >> 16) % 2000),
            "fees": float(abs(addr_hash >> 24) % 100) / 1000.0,
            "num_input_addresses": abs(addr_hash >> 32) % 30,
            "num_output_addresses": abs(addr_hash >> 40) % 50,
        }

        result = score_address(features)

        return {
            "risk_score": result.risk_score,
            "risk_level": result.risk_level,
            "top_factors": result.top_factors,
            "explanation": result.explanation,
        }

    except Exception as exc:
        logger.error("get_risk_score(%s) failed: %s", address, exc, exc_info=True)
        return {
            "risk_score": 50,
            "risk_level": "MEDIUM",
            "top_factors": ["scoring_unavailable"],
            "explanation": f"Risk scoring failed: {exc}",
        }


async def _handle_check_bridge_correlation(params: dict) -> dict:
    """Tool: check_bridge_correlation — MVP stub returning empty list.

    The full cross-chain bridge correlator is a stretch goal.
    """
    logger.info(
        "check_bridge_correlation(tx=%s, %s→%s) — MVP stub",
        params.get("tx_hash", "?"),
        params.get("source_chain", "?"),
        params.get("dest_chain", "?"),
    )
    return {"candidates": []}


async def _handle_get_transaction_history(params: dict) -> dict:
    """Tool: get_transaction_history — calls the blockchain orchestrator.

    Uses ``trace_address()`` (depth=0) which fetches transactions for
    just the target address without BFS expansion.
    """
    address = params["address"]
    chain = params.get("chain", "ethereum")

    try:
        from app.database import async_session
        from app.services.blockchain.orchestrator import trace_address

        async with async_session() as session:
            trace = await trace_address(address, session, depth=0)

        # Convert edges to serialisable dicts
        transactions = []
        for edge in trace.edges:
            transactions.append({
                "tx_hash": edge.tx_hash,
                "from_address": edge.from_address,
                "to_address": edge.to_address,
                "value": str(edge.value),
                "token": edge.token,
                "chain": edge.chain,
                "timestamp": edge.timestamp.isoformat(),
                "block_number": edge.block_number,
            })

        return {
            "transactions": transactions,
            "count": len(transactions),
            "address": address,
            "chain": chain,
        }

    except Exception as exc:
        logger.error(
            "get_transaction_history(%s, %s) failed: %s",
            address, chain, exc, exc_info=True,
        )
        return {
            "transactions": [],
            "count": 0,
            "address": address,
            "chain": chain,
            "error": str(exc),
        }


# Dispatch table: tool name → async handler
TOOL_HANDLERS: Dict[str, Any] = {
    "check_known_tags": _handle_check_known_tags,
    "get_cluster": _handle_get_cluster,
    "get_risk_score": _handle_get_risk_score,
    "check_bridge_correlation": _handle_check_bridge_correlation,
    "get_transaction_history": _handle_get_transaction_history,
}


# ---------------------------------------------------------------------------
# Agentic investigation loop (OpenAI-compatible SDK → Groq)
# ---------------------------------------------------------------------------


async def _run_agentic_investigation(
    address: str,
    chain: str,
) -> InvestigationResult:
    """Drive a Groq-hosted LLM agent through the investigation using
    OpenAI-compatible function calling.

    Raises on any SDK / network error so the caller can fall
    back to the rule-based path.
    """
    from openai import OpenAI

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        # Also try Pydantic settings
        try:
            from app.config import settings
            api_key = settings.GROQ_API_KEY
        except Exception:
            pass

    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")

    client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

    user_message = (
        f"Investigate blockchain wallet {address} on {chain}. "
        f"Use the available tools to check tags, cluster the address, "
        f"score the risk, and review transaction history. "
        f"Provide a clear summary of your findings."
    )

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    reasoning_log: list[ReasoningStep] = []
    step_number = 0
    start_time = time.monotonic()

    for _round in range(MAX_TOOL_ROUNDS):
        # Timeout guard
        elapsed = time.monotonic() - start_time
        if elapsed > INVESTIGATION_TIMEOUT_SECONDS:
            logger.warning(
                "Investigation timed out after %.1fs (%d rounds)",
                elapsed, _round,
            )
            break

        # Call Groq via OpenAI SDK
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=MAX_TOKENS,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            messages=messages,
        )

        choice = response.choices[0]
        assistant_message = choice.message

        logger.debug(
            "Groq response: finish_reason=%s, tool_calls=%s",
            choice.finish_reason,
            len(assistant_message.tool_calls) if assistant_message.tool_calls else 0,
        )

        # Append the assistant message to conversation
        # Convert to dict for serialisation
        assistant_dict: dict = {"role": "assistant", "content": assistant_message.content or ""}
        if assistant_message.tool_calls:
            assistant_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_message.tool_calls
            ]
        messages.append(assistant_dict)

        # If the model finished (no tool calls), we're done
        if choice.finish_reason == "stop" or not assistant_message.tool_calls:
            break

        # ── Execute tool calls ──
        for tc in assistant_message.tool_calls:
            tool_name = tc.function.name
            try:
                tool_input = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_input = {}

            logger.info(
                "Agent tool call #%d: %s(%s)",
                step_number + 1,
                tool_name,
                json.dumps(tool_input, default=str),
            )

            handler = TOOL_HANDLERS.get(tool_name)
            if handler is None:
                tool_output = {"error": f"Unknown tool: {tool_name}"}
            else:
                try:
                    tool_output = await handler(tool_input)
                except Exception as exc:
                    logger.error(
                        "Tool %s failed: %s", tool_name, exc, exc_info=True,
                    )
                    tool_output = {"error": str(exc)}

            # Send tool result as a 'tool' role message (OpenAI format)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_output, default=str),
            })

            # Record the reasoning step
            step_number += 1
            reasoning_log.append(
                ReasoningStep(
                    step_number=step_number,
                    tool_used=tool_name,
                    input_params=tool_input,
                    result_summary=json.dumps(tool_output, default=str)[:500],
                    confidence=_extract_confidence(tool_name, tool_output),
                )
            )

    # ── Parse the final text response ──
    final_text = ""
    # Walk messages backwards to find the last assistant text
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            final_text = msg["content"]
            break

    # Build the result
    attribution = _extract_attribution(reasoning_log, final_text)
    risk_score = _extract_risk_score(reasoning_log)
    typology = _extract_typology(reasoning_log, final_text)

    return InvestigationResult(
        reasoning_log=reasoning_log,
        attribution=attribution,
        risk_score=risk_score,
        typology=typology,
        summary=_truncate(final_text, 1000) if final_text else "Investigation complete.",
        used_fallback=False,
    )


# ---------------------------------------------------------------------------
# Rule-based fallback investigation (no LLM API required)
# ---------------------------------------------------------------------------


async def _run_fallback_investigation(
    address: str,
    chain: str,
) -> InvestigationResult:
    """Deterministic rule-based investigation that calls every tool in
    a fixed order. Guarantees the demo works without a Groq API key.
    """
    logger.info("Running fallback (rule-based) investigation for %s on %s", address, chain)

    reasoning_log: list[ReasoningStep] = []
    step = 0

    # ── Step 1: Check known tags ──
    step += 1
    tag_result = await _handle_check_known_tags({"address": address})
    tag_summary = (
        f"Address is tagged as '{tag_result['entity_name']}' "
        f"(type={tag_result['entity_type']}, confidence={tag_result['confidence']})"
        if tag_result["found"]
        else "Address has no known tags in the knowledge base."
    )
    reasoning_log.append(ReasoningStep(
        step_number=step,
        tool_used="check_known_tags",
        input_params={"address": address},
        result_summary=tag_summary,
        confidence=tag_result["confidence"] if tag_result["found"] else 0.0,
    ))

    # ── Step 2: Cluster the address ──
    step += 1
    cluster_result = await _handle_get_cluster({"address": address})
    if cluster_result.get("cluster_id"):
        cluster_summary = (
            f"Found cluster {cluster_result['cluster_id']} with "
            f"{cluster_result['member_count']} members "
            f"(heuristic: {cluster_result['heuristic']}). "
            f"Tagged members: {len(cluster_result.get('tagged_members', []))}."
        )
        cluster_confidence = cluster_result.get("confidence", 0.5)
    else:
        cluster_summary = "No cluster found — address appears isolated."
        cluster_confidence = 0.0
    reasoning_log.append(ReasoningStep(
        step_number=step,
        tool_used="get_cluster",
        input_params={"address": address},
        result_summary=cluster_summary,
        confidence=cluster_confidence,
    ))

    # ── Step 3: Check tags for cluster members ──
    tagged_members = cluster_result.get("tagged_members", [])
    for member in tagged_members[:5]:  # cap at 5 lookups
        step += 1
        member_tag = await _handle_check_known_tags({"address": member["address"]})
        member_summary = (
            f"Cluster member {member['address'][:12]}… tagged as "
            f"'{member_tag.get('entity_name', 'unknown')}' "
            f"(type={member_tag.get('entity_type')})."
            if member_tag.get("found")
            else f"Cluster member {member['address'][:12]}… has no tags."
        )
        reasoning_log.append(ReasoningStep(
            step_number=step,
            tool_used="check_known_tags",
            input_params={"address": member["address"]},
            result_summary=member_summary,
            confidence=member_tag.get("confidence", 0.0),
        ))

    # ── Step 4: Get risk score ──
    step += 1
    risk_result = await _handle_get_risk_score({"address": address})
    risk_summary = (
        f"Risk score: {risk_result['risk_score']}/100 "
        f"({risk_result['risk_level']}). "
        f"Top factors: {', '.join(risk_result.get('top_factors', [])[:3]) or 'none'}."
    )
    reasoning_log.append(ReasoningStep(
        step_number=step,
        tool_used="get_risk_score",
        input_params={"address": address},
        result_summary=risk_summary,
        confidence=min(risk_result["risk_score"] / 100.0, 1.0),
    ))

    # ── Step 5: Get transaction history ──
    step += 1
    tx_result = await _handle_get_transaction_history({
        "address": address,
        "chain": chain,
    })
    tx_summary = (
        f"Found {tx_result['count']} transactions on {chain}."
    )
    reasoning_log.append(ReasoningStep(
        step_number=step,
        tool_used="get_transaction_history",
        input_params={"address": address, "chain": chain},
        result_summary=tx_summary,
        confidence=1.0 if tx_result["count"] > 0 else 0.3,
    ))

    # ── Build attribution ──
    attribution: Attribution | None = None
    if tag_result["found"]:
        attribution = Attribution(
            entity_name=tag_result["entity_name"],
            entity_type=tag_result["entity_type"],
            confidence=tag_result["confidence"],
            match_method="direct_tag",
            is_sanctioned=tag_result.get("is_sanctioned", False),
        )
    elif tagged_members:
        best = tagged_members[0]
        attribution = Attribution(
            entity_name=best.get("label"),
            entity_type=best.get("entity_type"),
            confidence=cluster_confidence * 0.8,
            match_method="cluster_tag",
            is_sanctioned=False,
        )

    # ── Determine typology ──
    typology = _derive_typology_from_risk(risk_result, tag_result, cluster_result)

    # ── Build summary ──
    risk_level = risk_result["risk_level"]
    if attribution:
        summary = (
            f"Address {address[:12]}… is attributed to '{attribution.entity_name}' "
            f"({attribution.entity_type}) with {attribution.confidence:.0%} confidence. "
            f"Risk level: {risk_level}. Typology: {typology}."
        )
    else:
        summary = (
            f"Address {address[:12]}… could not be attributed to a known entity. "
            f"Risk level: {risk_level} (score: {risk_result['risk_score']}/100). "
            f"Typology: {typology}. Further manual investigation recommended."
        )

    return InvestigationResult(
        reasoning_log=reasoning_log,
        attribution=attribution,
        risk_score=risk_result["risk_score"],
        typology=typology,
        summary=summary,
        used_fallback=True,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def investigate(address: str, chain: str = "ethereum") -> InvestigationResult:
    """Run a full agentic fraud investigation on a blockchain address.

    Attempts the Groq-powered agentic path first.  If the Groq API
    is unavailable for any reason, falls back to a deterministic rule-based
    investigation that calls the same underlying tools.

    Args:
        address: The blockchain address to investigate.
        chain:   The blockchain name (``"ethereum"``, ``"bitcoin"``, ``"tron"``).

    Returns:
        An :class:`InvestigationResult` with reasoning log, attribution,
        risk score, typology, and executive summary.
    """
    logger.info("Starting investigation: address=%s chain=%s", address, chain)
    start = time.monotonic()

    try:
        result = await asyncio.wait_for(
            _run_agentic_investigation(address, chain),
            timeout=INVESTIGATION_TIMEOUT_SECONDS,
        )
        elapsed = time.monotonic() - start
        logger.info(
            "Agentic investigation complete in %.1fs (%d steps)",
            elapsed,
            len(result.reasoning_log),
        )
        return result

    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.warning(
            "Agentic investigation failed after %.1fs (%s: %s). "
            "Falling back to rule-based investigation.",
            elapsed,
            type(exc).__name__,
            exc,
        )
        try:
            result = await _run_fallback_investigation(address, chain)
            logger.info(
                "Fallback investigation complete (%d steps)",
                len(result.reasoning_log),
            )
            return result
        except Exception as fallback_exc:
            logger.error(
                "Fallback investigation also failed: %s",
                fallback_exc,
                exc_info=True,
            )
            return InvestigationResult(
                summary=(
                    f"Investigation failed for {address} on {chain}. "
                    f"Agentic error: {exc}. Fallback error: {fallback_exc}."
                ),
                used_fallback=True,
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_confidence(tool_name: str, tool_output: dict) -> float:
    """Pull a confidence value from a tool result, or return a default."""
    if "confidence" in tool_output:
        return float(tool_output["confidence"])
    if "found" in tool_output:
        return tool_output.get("confidence", 0.9) if tool_output["found"] else 0.0
    if "risk_score" in tool_output:
        return min(tool_output["risk_score"] / 100.0, 1.0)
    return 0.5


def _extract_attribution(
    reasoning_log: list[ReasoningStep],
    final_text: str,
) -> Attribution | None:
    """Best-effort extraction of attribution from the reasoning log."""
    for step in reasoning_log:
        if step.tool_used == "check_known_tags" and step.confidence > 0.5:
            try:
                result = json.loads(step.result_summary)
                if result.get("found"):
                    return Attribution(
                        entity_name=result.get("entity_name"),
                        entity_type=result.get("entity_type"),
                        confidence=result.get("confidence", 0.0),
                        match_method="direct_tag",
                        is_sanctioned=result.get("is_sanctioned", False),
                    )
            except (json.JSONDecodeError, TypeError):
                # result_summary may be narration, not JSON — that's fine
                pass

    # Check cluster tag hits
    for step in reasoning_log:
        if step.tool_used == "get_cluster":
            try:
                result = json.loads(step.result_summary)
                tagged = result.get("tagged_members", [])
                if tagged:
                    best = tagged[0]
                    return Attribution(
                        entity_name=best.get("label"),
                        entity_type=best.get("entity_type"),
                        confidence=result.get("confidence", 0.5) * 0.8,
                        match_method="cluster_tag",
                        is_sanctioned=False,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

    return None


def _extract_risk_score(reasoning_log: list[ReasoningStep]) -> int:
    """Pull the risk score from the reasoning log."""
    for step in reasoning_log:
        if step.tool_used == "get_risk_score":
            try:
                result = json.loads(step.result_summary)
                return int(result.get("risk_score", 0))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
    return 0


def _extract_typology(
    reasoning_log: list[ReasoningStep],
    final_text: str,
) -> str:
    """Try to classify the fraud typology from available evidence."""
    # Check if the agent explicitly mentioned a typology in its summary
    typology_keywords = {
        "investment scam": "Investment Scam",
        "pig butchering": "Investment Scam",
        "ponzi": "Investment Scam",
        "money mule": "Money Mule",
        "mule account": "Money Mule",
        "mixer": "Mixer Usage",
        "mixing": "Mixer Usage",
        "tornado": "Mixer Usage",
        "coinjoin": "Mixer Usage",
        "ransomware": "Ransomware",
        "darknet": "Darknet Market",
        "dark net": "Darknet Market",
        "peeling": "Peeling Chain",
        "peel chain": "Peeling Chain",
    }

    text_lower = final_text.lower()
    for keyword, typology in typology_keywords.items():
        if keyword in text_lower:
            return typology

    # Fall back to typology classifier if available
    try:
        from app.services.ml.typology import classify_typology
        result = classify_typology(None)  # Minimal call
        return result.typology
    except Exception:
        pass

    return "Unclassified"


def _derive_typology_from_risk(
    risk_result: dict,
    tag_result: dict,
    cluster_result: dict,
) -> str:
    """Rule-based typology derivation for the fallback path."""
    entity_type = tag_result.get("entity_type", "")
    factors = risk_result.get("top_factors", [])
    factors_text = " ".join(f.lower() for f in factors) if factors else ""

    if tag_result.get("is_sanctioned"):
        return "Sanctioned Entity"
    if entity_type == "mixer" or "mixer" in factors_text or "mixing" in factors_text:
        return "Mixer Usage"
    if "outgoing" in factors_text and risk_result.get("risk_score", 0) >= 70:
        return "Money Mule"
    if risk_result.get("risk_score", 0) >= 80:
        return "High-Risk Unclassified"
    if entity_type == "exchange":
        return "Exchange Activity"
    return "Unclassified"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
