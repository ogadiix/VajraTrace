from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

# Setup basic logging
logger = logging.getLogger(__name__)

# Try importing the required models, but allow falling back to dict processing
try:
    from app.services.blockchain.models import TraceGraphResult
    HAS_MODELS = True
except ImportError:
    logger.warning("Could not import app.services.blockchain.models.TraceGraphResult, running in dict-only mode.")
    HAS_MODELS = False


@dataclass
class TypologyResult:
    """Represents the result of a typology classification."""
    typology: str
    confidence: float
    evidence: str
    indicators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "typology": self.typology,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "indicators": self.indicators
        }


class TypologyClassifier:
    """Rule-based classifier to identify potential fraud typologies in blockchain traces."""

    def _extract_data(self, trace_result: Any) -> tuple[list[Any], list[Any]]:
        """Helper to extract nodes and edges whether trace_result is an object or dict."""
        if HAS_MODELS and isinstance(trace_result, TraceGraphResult):
            return trace_result.nodes, trace_result.edges
        elif isinstance(trace_result, dict):
            return trace_result.get("nodes", []), trace_result.get("edges", [])
        else:
            logger.error("Unsupported trace_result format.")
            return [], []

    def _get_node_attribute(self, node: Any, attr: str) -> Any:
        if isinstance(node, dict):
            return node.get(attr)
        return getattr(node, attr, None)

    def _get_edge_attribute(self, edge: Any, attr: str) -> Any:
        if isinstance(edge, dict):
            return edge.get(attr)
        return getattr(edge, attr, None)

    def _check_investment_scam(self, nodes: list[Any], edges: list[Any]) -> Optional[TypologyResult]:
        """
        Look for: slow value accumulation over weeks (many small inflows spread over time), 
        then sudden large withdrawal.
        Check: if total_received builds up gradually (>5 incoming txns over >7 day span) 
        AND there's a single outflow > 50% of total_received.
        """
        best_confidence = 0.0
        evidence = ""
        indicators = []

        for node in nodes:
            address = self._get_node_attribute(node, 'address')
            if not address:
                continue
            
            incoming_edges = [e for e in edges if self._get_edge_attribute(e, 'to_address') == address]
            outgoing_edges = [e for e in edges if self._get_edge_attribute(e, 'from_address') == address]
            
            if len(incoming_edges) > 5 and len(outgoing_edges) >= 1:
                # Check timespan
                timestamps = [self._get_edge_attribute(e, 'timestamp') for e in incoming_edges if self._get_edge_attribute(e, 'timestamp')]
                if timestamps:
                    try:
                        # Parsing timestamps
                        parsed_times = []
                        for ts in timestamps:
                            if isinstance(ts, str):
                                parsed_times.append(datetime.fromisoformat(ts.replace('Z', '+00:00')))
                            elif isinstance(ts, datetime):
                                parsed_times.append(ts)
                                
                        if parsed_times:
                            min_time = min(parsed_times)
                            max_time = max(parsed_times)
                            timespan = (max_time - min_time).days
                            
                            if timespan > 7:
                                total_received = sum((Decimal(str(self._get_edge_attribute(e, 'value') or 0))) for e in incoming_edges)
                                if total_received > 0:
                                    max_outflow = max((Decimal(str(self._get_edge_attribute(e, 'value') or 0))) for e in outgoing_edges)
                                    if max_outflow > (total_received * Decimal("0.5")):
                                        best_confidence = 0.8
                                        evidence = f"Node {address} shows gradual accumulation ({len(incoming_edges)} txs over {timespan} days) followed by a large withdrawal."
                                        indicators = ["Slow accumulation", "Sudden large withdrawal"]
                                        break
                    except Exception as e:
                        logger.debug(f"Error parsing timestamps: {e}")

        if best_confidence > 0:
            return TypologyResult("Investment Scam", best_confidence, evidence, indicators)
        return None

    def _check_ransomware(self, nodes: list[Any], edges: list[Any]) -> Optional[TypologyResult]:
        """
        Look for: single large incoming payment, minimal hops to exchange.
        Check: <= 3 incoming txns, at least one large (>1 BTC equivalent), and rapid outflow to few addresses.
        """
        for node in nodes:
            address = self._get_node_attribute(node, 'address')
            incoming = [e for e in edges if self._get_edge_attribute(e, 'to_address') == address]
            outgoing = [e for e in edges if self._get_edge_attribute(e, 'from_address') == address]

            if 0 < len(incoming) <= 3 and len(outgoing) > 0:
                has_large = any(Decimal(str(self._get_edge_attribute(e, 'value') or 0)) > Decimal("1.0") for e in incoming)
                if has_large:
                    unique_out_dest = set(self._get_edge_attribute(e, 'to_address') for e in outgoing)
                    if len(unique_out_dest) <= 3:
                        return TypologyResult(
                            "Ransomware", 
                            0.85, 
                            f"Address {address} received large payment and rapidly forwarded it to {len(unique_out_dest)} addresses.",
                            ["Few large incoming txs", "Rapid consolidation/forwarding"]
                        )
        return None

    def _check_phishing(self, nodes: list[Any], edges: list[Any]) -> Optional[TypologyResult]:
        """
        Look for: many small incoming transactions from many different addresses.
        Check: >10 unique senders, small average value, high tx count.
        """
        for node in nodes:
            address = self._get_node_attribute(node, 'address')
            incoming = [e for e in edges if self._get_edge_attribute(e, 'to_address') == address]
            
            if len(incoming) > 10:
                unique_senders = set(self._get_edge_attribute(e, 'from_address') for e in incoming)
                if len(unique_senders) > 10:
                    return TypologyResult(
                        "Phishing",
                        0.75,
                        f"Address {address} received transactions from {len(unique_senders)} unique addresses.",
                        ["Many unique senders", "High transaction volume"]
                    )
        return None

    def _check_pig_butchering(self, nodes: list[Any], edges: list[Any]) -> Optional[TypologyResult]:
        """
        Look for: increasing amounts over time from same victim address, eventual drain.
        Check: repeated sends from same address with increasing values, then large outflow.
        """
        for node in nodes:
            address = self._get_node_attribute(node, 'address')
            incoming = [e for e in edges if self._get_edge_attribute(e, 'to_address') == address]
            
            sender_txs = {}
            for e in incoming:
                sender = self._get_edge_attribute(e, 'from_address')
                if sender not in sender_txs:
                    sender_txs[sender] = []
                val = Decimal(str(self._get_edge_attribute(e, 'value') or 0))
                sender_txs[sender].append(val)
                
            for sender, vals in sender_txs.items():
                if len(vals) >= 3:
                    if vals[0] < vals[-1] and vals[1] > 0:
                        outgoing = [e for e in edges if self._get_edge_attribute(e, 'from_address') == address]
                        if outgoing:
                            max_out = max(Decimal(str(self._get_edge_attribute(e, 'value') or 0)) for e in outgoing)
                            if max_out > sum(vals) * Decimal("0.5"):
                                return TypologyResult(
                                    "Pig Butchering",
                                    0.8,
                                    f"Address {address} received increasing amounts from {sender}, followed by large drain.",
                                    ["Increasing deposit amounts", "Eventual drain"]
                                )
        return None

    def _check_money_mule(self, nodes: list[Any], edges: list[Any]) -> Optional[TypologyResult]:
        """
        Look for: rapid pass-through (<1 hour hold time), minimal value change.
        Check: time between first_seen and last_seen is very short, total_received ≈ total_sent.
        """
        for node in nodes:
            address = self._get_node_attribute(node, 'address')
            first_seen = self._get_node_attribute(node, 'first_seen')
            last_seen = self._get_node_attribute(node, 'last_seen')
            tot_recv = Decimal(str(self._get_node_attribute(node, 'total_received') or 0))
            tot_sent = Decimal(str(self._get_node_attribute(node, 'total_sent') or 0))
            
            if first_seen and last_seen and tot_recv > 0:
                try:
                    if isinstance(first_seen, str):
                        first_seen = datetime.fromisoformat(first_seen.replace('Z', '+00:00'))
                    if isinstance(last_seen, str):
                        last_seen = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                        
                    if isinstance(first_seen, datetime) and isinstance(last_seen, datetime):
                        diff = (last_seen - first_seen).total_seconds()
                        if 0 <= diff <= 3600:
                            if tot_sent > 0 and abs(tot_recv - tot_sent) / tot_recv < Decimal("0.05"):
                                return TypologyResult(
                                    "Money Mule",
                                    0.9,
                                    f"Address {address} exhibits rapid pass-through behavior with near 1:1 in/out ratio.",
                                    ["Rapid pass-through", "High velocity", "Minimal retained value"]
                                )
                except Exception as e:
                    logger.debug(f"Error parsing dates for money mule check: {e}")
        return None

    def _check_darknet(self, nodes: list[Any], edges: list[Any], cluster_info: Optional[Dict] = None) -> Optional[TypologyResult]:
        """
        Look for: interaction with known mixer/tumbler addresses.
        Check: if any connected node has label containing 'mixer', 'tumbler', 'tornado', 'chipmixer', 'wasabi'.
        Also check: many equal-sized outputs (mixing pattern), or known darknet marketplace labels.
        """
        dark_keywords = ['mixer', 'tumbler', 'tornado', 'chipmixer', 'wasabi', 'darknet', 'market']
        
        for node in nodes:
            label = self._get_node_attribute(node, 'label')
            if label and isinstance(label, str):
                label_lower = label.lower()
                if any(k in label_lower for k in dark_keywords):
                    return TypologyResult(
                        "Darknet / Mixer",
                        0.95,
                        f"Interaction with known high-risk entity: {label}",
                        ["Mixer/Darknet interaction"]
                    )
        
        tx_outputs = {}
        for e in edges:
            tx = self._get_edge_attribute(e, 'tx_hash')
            val = self._get_edge_attribute(e, 'value')
            if tx and val is not None:
                if tx not in tx_outputs:
                    tx_outputs[tx] = []
                tx_outputs[tx].append(Decimal(str(val)))
                
        for tx, outputs in tx_outputs.items():
            if len(outputs) >= 5:
                if all(o == outputs[0] for o in outputs):
                    return TypologyResult(
                        "Darknet / Mixer",
                        0.7,
                        f"Transaction {tx} shows mixing pattern with {len(outputs)} equal-sized outputs.",
                        ["Equal-sized outputs", "Potential mixing"]
                    )

        return None

    def classify(self, trace_result: Any, cluster_info: Optional[Dict] = None) -> TypologyResult:
        """
        Main method to classify a trace result into a fraud typology.
        Returns the typology with the highest confidence.
        If no pattern matches clearly, returns 'Unclassified'.
        """
        nodes, edges = self._extract_data(trace_result)
        
        if not nodes or not edges:
            return TypologyResult('Unclassified', 0.0, 'Insufficient data to classify', [])

        results = []
        
        checks = [
            self._check_investment_scam,
            self._check_ransomware,
            self._check_phishing,
            self._check_pig_butchering,
            self._check_money_mule,
        ]

        for check in checks:
            try:
                res = check(nodes, edges)
                if res:
                    results.append(res)
            except Exception as e:
                logger.error(f"Error running typology check {check.__name__}: {e}")
                
        try:
            res = self._check_darknet(nodes, edges, cluster_info)
            if res:
                results.append(res)
        except Exception as e:
            logger.error(f"Error running typology check _check_darknet: {e}")

        if not results:
            return TypologyResult('Unclassified', 0.0, 'No clear fraud typology pattern detected', [])

        best_result = max(results, key=lambda r: r.confidence)

        if best_result.confidence < 0.3:
            return TypologyResult('Unclassified', 0.0, 'No clear fraud typology pattern detected', [])

        return best_result


def classify_typology(trace_result: Any, cluster_info: Optional[Dict] = None) -> TypologyResult:
    """Convenience method to classify a trace result."""
    classifier = TypologyClassifier()
    return classifier.classify(trace_result, cluster_info)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Mock data for testing
    mock_nodes = [
        {"address": "0xVictim", "label": None, "first_seen": "2023-01-01T00:00:00Z", "last_seen": "2023-01-10T00:00:00Z", "total_received": 100, "total_sent": 95},
        {"address": "0xMule", "label": None, "first_seen": "2023-01-05T12:00:00Z", "last_seen": "2023-01-05T12:30:00Z", "total_received": 50, "total_sent": 49.9},
        {"address": "0xMixer", "label": "Tornado Cash", "first_seen": None, "last_seen": None, "total_received": 0, "total_sent": 0}
    ]
    
    mock_edges = [
        {"from_address": "0xVictim", "to_address": "0xMule", "tx_hash": "0x1", "value": 50, "timestamp": "2023-01-05T12:05:00Z"},
        {"from_address": "0xMule", "to_address": "0xMixer", "tx_hash": "0x2", "value": 49.9, "timestamp": "2023-01-05T12:15:00Z"}
    ]
    
    mock_trace = {
        "nodes": mock_nodes,
        "edges": mock_edges
    }
    
    print("Running classification on mock trace...")
    result = classify_typology(mock_trace)
    print(f"Classification result: {result}")
