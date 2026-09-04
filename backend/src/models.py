"""
Core data models for Small-Merchant AI Readiness Agent.
All models use Pydantic v2 with full validation.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class PaymentMethod(str, Enum):
    UPI = "UPI"
    CARD = "card"
    NETBANKING = "netbanking"

class PaymentStatus(str, Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"

class SessionOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    ACTIVE = "ACTIVE"

class CatalogStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHING = "PUBLISHING"  # Embeddings generating in background
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

class EvidenceStatus(str, Enum):
    FOUND = "FOUND"
    MISSING = "MISSING"
    PARTIAL = "PARTIAL"

class PermissionDenialReason(str, Enum):
    BUYER_LIMIT_EXCEEDED = "BUYER_LIMIT_EXCEEDED"
    MERCHANT_CAP_EXCEEDED = "MERCHANT_CAP_EXCEEDED"
    PRODUCT_EXCLUDED = "PRODUCT_EXCLUDED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    PAYMENT_ATTEMPTS_EXCEEDED = "PAYMENT_ATTEMPTS_EXCEEDED"

class StepType(str, Enum):
    SESSION_STARTED = "session_started"
    SEARCH_CATALOG = "search_catalog"
    OPTIONS_PRESENTED = "options_presented"
    PRODUCT_SELECTED = "product_selected"
    AVAILABILITY_CHECKED = "availability_checked"
    PERMISSION_CHECKED = "permission_checked"
    CONFIRMATION_GATE = "confirmation_gate"
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_STATUS_POLLED = "payment_status_polled"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    RETRY_INITIATED = "retry_initiated"
    SESSION_COMPLETE = "session_complete"
    ERROR = "error"
    FALLBACK_USED = "fallback_used"


# ── Catalog Models ─────────────────────────────────────────────────────────────

class ShippingOption(BaseModel):
    method: str = "standard"
    days: int = 5
    cost_inr: float = 0.0

class PaymentConstraints(BaseModel):
    min_order_inr: float = 0.0
    max_order_inr: float = 100000.0
    accepted_methods: List[PaymentMethod] = [PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.NETBANKING]

class NormalizedProduct(BaseModel):
    product_id: str = Field(default_factory=lambda: f"prod_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    price_inr: float = Field(..., gt=0, lt=1_000_000)
    availability: bool = True
    stock_count: int = Field(default=0, ge=0)
    category: str = "Other"
    payment_constraints: PaymentConstraints = Field(default_factory=PaymentConstraints)
    return_policy_days: int = 0
    shipping_options: List[ShippingOption] = Field(default_factory=lambda: [ShippingOption()])
    embedding: Optional[List[float]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_format: str = "form"

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("description")
    @classmethod
    def truncate_description(cls, v: str) -> str:
        return v.strip()[:500] if v else ""

class AgentPermissions(BaseModel):
    max_transaction_inr: float = Field(default=10000.0, ge=0)
    requires_confirmation_above_inr: float = Field(default=500.0, ge=0)
    auto_approve_below_inr: float = Field(default=0.0, ge=0)  # Always 0 — confirmation always required
    excluded_product_ids: List[str] = Field(default_factory=list)

class MerchantCatalog(BaseModel):
    merchant_id: str = Field(default_factory=lambda: f"merch_{uuid.uuid4().hex[:8]}")
    merchant_name: str
    catalog_version: str = "v1.0"
    products: List[NormalizedProduct] = Field(default_factory=list)
    agent_permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    status: CatalogStatus = CatalogStatus.DRAFT
    onboarding_source: str = "form"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ValidationError(BaseModel):
    product_index: Optional[int] = None
    product_id: Optional[str] = None
    code: str
    field: Optional[str] = None
    message: str

class ValidationWarning(BaseModel):
    product_index: Optional[int] = None
    product_id: Optional[str] = None
    code: str
    message: str

class NormalizationResult(BaseModel):
    success: bool
    products: List[NormalizedProduct] = Field(default_factory=list)
    errors: List[ValidationError] = Field(default_factory=list)
    warnings: List[ValidationWarning] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)


# ── Search Models ──────────────────────────────────────────────────────────────

class ProductSearchResult(BaseModel):
    product: NormalizedProduct
    similarity_score: float
    rank: int

class SearchResponse(BaseModel):
    query: str
    merchant_id: str
    results: List[ProductSearchResult]
    total_searched: int
    embedding_used: bool


# ── Agent & Session Models ─────────────────────────────────────────────────────

class BuyerSession(BaseModel):
    model_config = {"extra": "allow"}
    session_id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:12]}")
    merchant_id: str
    purchase_intent: str
    spending_limit_inr: float = 2000.0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    payment_attempts: int = 0
    confirmation_gate_hit: bool = False
    status: SessionOutcome = SessionOutcome.ACTIVE
    ai_provider_used: Optional[str] = None
    payment_id: Optional[str] = None
    product_purchased: Optional[str] = None
    amount_inr: Optional[float] = None
    error_message: Optional[str] = None

class AuditEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sequence: int
    step: StepType
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    reasoning: Optional[str] = None
    confidence: Optional[float] = None
    latency_ms: Optional[int] = None
    model_used: Optional[str] = None
    error: Optional[str] = None

class SessionOutcomeRecord(BaseModel):
    status: SessionOutcome
    payment_id: Optional[str] = None
    product_purchased: Optional[str] = None
    amount_inr: Optional[float] = None
    confirmation_gate_hit: bool = False
    payment_attempts: int = 0
    total_session_ms: Optional[int] = None
    ai_provider_used: Optional[str] = None
    error_message: Optional[str] = None

class FullAuditTrail(BaseModel):
    session_id: str
    merchant_id: str
    merchant_name: str
    started_at: datetime
    completed_at: Optional[datetime]
    purchase_intent: str
    entries: List[AuditEntry]
    outcome: Optional[SessionOutcomeRecord] = None


# ── Permission Models ──────────────────────────────────────────────────────────

class PermissionResult(BaseModel):
    allowed: bool
    confirmation_required: bool = True  # Always True — never skip
    reason: Optional[PermissionDenialReason] = None
    message: Optional[str] = None


# ── Payment Models ─────────────────────────────────────────────────────────────

class PaymentResult(BaseModel):
    payment_id: str
    order_id: str
    status: PaymentStatus
    amount_inr: float
    payment_method: PaymentMethod
    created_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    is_test_mode: bool = True


# ── Evaluation Models ─────────────────────────────────────────────────────────

class ScenarioCategory(str, Enum):
    HAPPY_PATH = "happy_path"
    AMBIGUOUS_INTENT = "ambiguous_intent"
    PAYMENT_FAILURE = "payment_failure"

class GroundTruth(BaseModel):
    expected_product_id: Optional[str] = None
    expected_price_inr: Optional[float] = None
    expected_outcome: SessionOutcome
    confirmation_gate_must_fire: bool = True
    max_payment_attempts_allowed: int = 2
    options_should_be_presented: Optional[bool] = None
    min_options_presented: Optional[int] = None

class TestScenario(BaseModel):
    scenario_id: str
    category: ScenarioCategory
    purchase_intent: str
    merchant_id: str
    buyer_spending_limit_inr: float
    payment_mock: Optional[str] = None  # FAIL_FIRST_ATTEMPT, FAIL_ALL, etc.
    ground_truth: GroundTruth

class RunResult(BaseModel):
    run_id: int
    scenario_id: str
    category: ScenarioCategory
    outcome: SessionOutcome
    passed: bool
    confirmation_gate_fired: bool
    payment_attempts: int
    stopping_rule_compliant: bool
    audit_trail_complete: bool
    steps_to_payment: int
    session_ms: int
    ai_provider_used: Optional[str] = None
    failure_reason: Optional[str] = None

class EvaluationMetrics(BaseModel):
    total_runs: int
    successful_runs: int
    end_to_end_success_rate: float
    confirmation_gate_hit_rate: float
    stopping_rule_compliance: float
    audit_trail_completeness: float
    avg_steps_to_payment: float
    avg_session_time_ms: float
    scenario_breakdown: Dict[str, Any]
    honest_failures: List[str]
    
    @property
    def pass_rate(self) -> float:
        return self.end_to_end_success_rate

class EvaluationResult(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_scenarios: int
    runs: List[RunResult]
    metrics: Optional[EvaluationMetrics] = None
    output_file: Optional[str] = None


# ── API Request/Response Models ────────────────────────────────────────────────

class OnboardCSVRequest(BaseModel):
    merchant_name: str = Field(..., min_length=1, max_length=200)

class OnboardSheetsRequest(BaseModel):
    merchant_name: str = Field(..., min_length=1, max_length=200)
    sheets_url: str

class OnboardManualRequest(BaseModel):
    merchant_name: str = Field(..., min_length=1, max_length=200)
    products: List[Dict[str, Any]]

class OnboardURLRequest(BaseModel):
    merchant_name: str = Field(..., min_length=1, max_length=200)
    product_page_url: str

class PublishCatalogRequest(BaseModel):
    agent_permissions: AgentPermissions = Field(default_factory=AgentPermissions)

class CreateSessionRequest(BaseModel):
    merchant_id: str
    purchase_intent: str
    spending_limit_inr: float = Field(default=2000.0, ge=1, le=100000)

class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str

class ConfirmPurchaseRequest(BaseModel):
    session_id: str
    confirmed: bool
    selected_product_id: Optional[str] = None
