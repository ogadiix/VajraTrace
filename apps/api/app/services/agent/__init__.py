"""VajraTrace Agent — agentic investigation reasoner.

Main entry point::

    from app.services.agent import investigate

    result = await investigate("0xdead...beef", chain="ethereum")
"""

from app.services.agent.investigator import (
    Attribution,
    InvestigationResult,
    ReasoningStep,
    investigate,
)

__all__ = [
    "Attribution",
    "InvestigationResult",
    "ReasoningStep",
    "investigate",
]
