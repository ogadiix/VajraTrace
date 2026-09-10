"""SQLAlchemy 2.0 ORM models for VajraTrace."""

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class ChainEnum(str, enum.Enum):
    BTC = 'BTC'
    ETH = 'ETH'
    TRON = 'TRON'

class CaseStatus(str, enum.Enum):
    SUBMITTED = 'SUBMITTED'
    INGESTING = 'INGESTING'
    CLUSTERING = 'CLUSTERING'
    CORRELATING = 'CORRELATING'
    ATTRIBUTING = 'ATTRIBUTING'
    SCORING = 'SCORING'
    NARRATING = 'NARRATING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'

class HeuristicEnum(str, enum.Enum):
    MULTI_INPUT = 'MULTI_INPUT'
    CHANGE_ADDRESS = 'CHANGE_ADDRESS'
    PEELING_CHAIN = 'PEELING_CHAIN'
    DEPOSIT_REUSE = 'DEPOSIT_REUSE'
    TIMING_AMOUNT_BRIDGE = 'TIMING_AMOUNT_BRIDGE'
    MANUAL = 'MANUAL'

class EntityTypeEnum(str, enum.Enum):
    EXCHANGE = 'EXCHANGE'
    VASP = 'VASP'
    MIXER = 'MIXER'
    DARKNET_MARKET = 'DARKNET_MARKET'
    RANSOMWARE = 'RANSOMWARE'
    SCAM = 'SCAM'
    SANCTIONED = 'SANCTIONED'
    P2P = 'P2P'
    DEFI_PROTOCOL = 'DEFI_PROTOCOL'
    BRIDGE = 'BRIDGE'
    UNKNOWN = 'UNKNOWN'

class TagSourceEnum(str, enum.Enum):
    OFAC_SDN = 'OFAC_SDN'
    GRAPHSENSE_TAGPACK = 'GRAPHSENSE_TAGPACK'
    MANUAL_CURATED = 'MANUAL_CURATED'
    COMMUNITY = 'COMMUNITY'
    ML_PREDICTED = 'ML_PREDICTED'

class EvidenceActionEnum(str, enum.Enum):
    FETCH_TX_HISTORY = 'FETCH_TX_HISTORY'
    CLUSTER_ADDRESS = 'CLUSTER_ADDRESS'
    DETECT_BRIDGE_HOP = 'DETECT_BRIDGE_HOP'
    TAG_LOOKUP = 'TAG_LOOKUP'
    SANCTIONS_CHECK = 'SANCTIONS_CHECK'
    RISK_SCORE = 'RISK_SCORE'
    AGENT_NARRATION = 'AGENT_NARRATION'
    REPORT_GENERATED = 'REPORT_GENERATED'


class Base(DeclarativeBase):
    pass


class RawTransaction(Base):
    __tablename__ = "raw_transactions"
    __table_args__ = (
        UniqueConstraint("address", "chain", "api_source", "endpoint", name="uq_raw_cache"),
        Index("idx_raw_tx_lookup", "address", "chain", "api_source", "endpoint"),
        Index("idx_raw_tx_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    chain: Mapped[ChainEnum] = mapped_column(Enum(ChainEnum, name="chain_enum"), nullable=False)
    api_source: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(256), nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="200")


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (
        UniqueConstraint("address", "chain", name="uq_address_chain"),
        Index("idx_addr_chain", "chain"),
        Index("idx_addr_last_seen", "last_seen", postgresql_using="btree", postgresql_ops={"last_seen": "DESC"}),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    chain: Mapped[ChainEnum] = mapped_column(Enum(ChainEnum, name="chain_enum"), nullable=False)
    first_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    total_in: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False, server_default="0")
    total_out: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False, server_default="0")
    tx_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_contract: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Cluster(Base):
    __tablename__ = "clusters"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1"),
        Index("idx_cluster_heuristic", "heuristic_used"),
        Index("idx_cluster_merged", "merged_into", postgresql_where=Column("merged_into").isnot(None)),
    )

    cluster_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    label: Mapped[Optional[str]] = mapped_column(String(256))
    heuristic_used: Mapped[HeuristicEnum] = mapped_column(Enum(HeuristicEnum, name="heuristic_enum"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(precision=24), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    merged_into: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.cluster_id", ondelete="SET NULL"))


class ClusterMember(Base):
    __tablename__ = "cluster_members"
    __table_args__ = (
        UniqueConstraint("cluster_id", "address_id", name="uq_cluster_address"),
        CheckConstraint("confidence >= 0 AND confidence <= 1"),
        Index("idx_cm_cluster", "cluster_id"),
        Index("idx_cm_address", "address_id"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    cluster_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.cluster_id", ondelete="CASCADE"), nullable=False)
    address_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("addresses.id", ondelete="CASCADE"), nullable=False)
    joined_via: Mapped[HeuristicEnum] = mapped_column(Enum(HeuristicEnum, name="heuristic_enum"), nullable=False)
    evidence_tx: Mapped[Optional[str]] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column(Float(precision=24), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1"),
        CheckConstraint("(address_id IS NOT NULL) OR (cluster_id IS NOT NULL)", name="chk_tag_target"),
        Index("idx_tag_address", "address_id", postgresql_where=Column("address_id").isnot(None)),
        Index("idx_tag_cluster", "cluster_id", postgresql_where=Column("cluster_id").isnot(None)),
        Index("idx_tag_entity_name", "entity_name", postgresql_using="gin", postgresql_ops={"entity_name": "gin_trgm_ops"}),
        Index("idx_tag_sanctioned", "is_sanctioned", postgresql_where=Column("is_sanctioned") == True),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    address_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("addresses.id", ondelete="CASCADE"))
    cluster_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.cluster_id", ondelete="CASCADE"))
    entity_name: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_type: Mapped[EntityTypeEnum] = mapped_column(Enum(EntityTypeEnum, name="entity_type_enum"), nullable=False)
    source: Mapped[TagSourceEnum] = mapped_column(Enum(TagSourceEnum, name="tag_source_enum"), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float(precision=24), nullable=False)
    is_sanctioned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint("risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 1)"),
        Index("idx_case_status", "status"),
        Index("idx_case_address", "reported_address", "reported_chain"),
        Index("idx_case_created", "created_at", postgresql_using="btree", postgresql_ops={"created_at": "DESC"}),
    )

    case_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    reported_address: Mapped[str] = mapped_column(String(128), nullable=False)
    reported_chain: Mapped[ChainEnum] = mapped_column(Enum(ChainEnum, name="chain_enum"), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus, name="case_status"), nullable=False, server_default="SUBMITTED")
    risk_score: Mapped[Optional[float]] = mapped_column(Float(precision=24))
    attributed_entity: Mapped[Optional[str]] = mapped_column(String(256))
    typology: Mapped[Optional[str]] = mapped_column(String(128))
    investigator_notes: Mapped[Optional[str]] = mapped_column(Text)
    submitted_by: Mapped[Optional[str]] = mapped_column(String(256))
    report_pdf_path: Mapped[Optional[str]] = mapped_column(Text)
    report_hash: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class EvidenceChain(Base):
    __tablename__ = "evidence_chain"
    __table_args__ = (
        UniqueConstraint("case_id", "step_number", name="uq_case_step"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)"),
        Index("idx_evidence_case", "case_id", "step_number"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    case_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[EvidenceActionEnum] = mapped_column(Enum(EvidenceActionEnum, name="evidence_action_enum"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    result_summary: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Float(precision=24))
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    shap_values: Mapped[Optional[dict]] = mapped_column(JSONB)
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64))
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TraceResult(Base):
    __tablename__ = "trace_results"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_trace_case"),
        CheckConstraint("confidence >= 0 AND confidence <= 1"),
        CheckConstraint("risk_score >= 0 AND risk_score <= 1"),
        Index("idx_trace_case", "case_id"),
        Index("idx_trace_vasp", "attributed_vasp"),
        Index("idx_trace_risk", "risk_score", postgresql_using="btree", postgresql_ops={"risk_score": "DESC"}),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    case_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False)
    address_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("addresses.id"))
    cluster_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.cluster_id"))
    attributed_vasp: Mapped[Optional[str]] = mapped_column(String(256))
    entity_type: Mapped[Optional[EntityTypeEnum]] = mapped_column(Enum(EntityTypeEnum, name="entity_type_enum"))
    confidence: Mapped[float] = mapped_column(Float(precision=24), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float(precision=24), nullable=False)
    typology: Mapped[Optional[str]] = mapped_column(String(128))
    shap_explanation: Mapped[Optional[dict]] = mapped_column(JSONB)
    bridge_hops: Mapped[Optional[dict]] = mapped_column(JSONB)
    sanctions_match: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sanctions_details: Mapped[Optional[dict]] = mapped_column(JSONB)
    agent_narrative: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
