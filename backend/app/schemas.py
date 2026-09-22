from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

class EntityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    jurisdiction: str = Field(min_length=1, max_length=100)
    entity_type: str = Field(pattern="^(parent|holdco|ip_co|opco)$")
    parent_entity_id: int | None = None
    ownership_pct: Decimal | None = Field(default=None, ge=0, le=100)
    incorporation_date: date | None = None
    tax_id: str | None = None

class EntityOut(EntityCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class SubstanceCreate(BaseModel):
    period: date
    local_employee_count: int = Field(ge=0)
    has_local_office: bool = False
    decision_evidence_notes: str | None = None
    board_meetings: list[dict] = Field(default_factory=list)

class PillarTwoCreate(BaseModel):
    jurisdiction: str
    period: date
    globe_income: Decimal | None = Field(default=None, ge=0)
    covered_taxes: Decimal | None = Field(default=None, ge=0)
    effective_tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    qdmtt_applicable: bool = False
    safe_harbour_type: str | None = None
    gir_filing_deadline: date | None = None
    gir_filed: bool = False

    @model_validator(mode="after")
    def validate_etr(self):
        if self.globe_income is not None and self.globe_income == 0 and self.covered_taxes not in (None, Decimal(0)):
            raise ValueError("covered_taxes must be zero when globe_income is zero")
        return self

class ComplianceCreate(BaseModel):
    obligation_type: str
    jurisdiction: str
    deadline: date
    status: str = Field(default="pending", pattern="^(pending|filed|overdue)$")

class TransactionCreate(BaseModel):
    from_entity_id: int
    to_entity_id: int
    type: str = Field(pattern="^(royalty|dividend|interest|goods|services)$")
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    transaction_date: date
    stated_price: Decimal
    benchmark_low: Decimal
    benchmark_high: Decimal
    tp_documentation_link: HttpUrl | None = None

    @model_validator(mode="after")
    def validate_benchmark(self):
        if self.benchmark_low > self.benchmark_high:
            raise ValueError("benchmark_low cannot exceed benchmark_high")
        return self

class TransactionStageUpdate(BaseModel):
    stage: str = Field(pattern="^(pricing|invoice|tax_treatment|settlement|evidence)$")
    invoice_reference: str | None = None
    tax_treatment_notes: str | None = None
    settled_date: date | None = None
    tp_documentation_link: HttpUrl | None = None

class InvoiceLineCreate(BaseModel):
    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)

class InvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal

class InvoiceCreate(BaseModel):
    invoice_type: str = Field(default="standard", pattern="^(standard|credit_note|debit_note)$")
    currency: str = Field(min_length=3, max_length=3)
    issue_date: date | None = None
    due_date: date | None = None
    related_invoice_id: int | None = None
    notes: str | None = None
    lines: list[InvoiceLineCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_related_invoice(self):
        if self.invoice_type in ("credit_note", "debit_note") and self.related_invoice_id is None:
            raise ValueError("credit_note and debit_note invoices must reference related_invoice_id")
        if self.due_date is not None and self.issue_date is not None and self.due_date < self.issue_date:
            raise ValueError("due_date cannot be before issue_date")
        return self

class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transaction_id: int
    created_by_actor: str
    invoice_number: str
    invoice_type: str
    status: str
    currency: str
    issue_date: date | None
    accounting_date: date | None
    posting_date: date | None
    settled_date: date | None
    due_date: date | None
    posted_at: datetime | None
    approval_state: str
    tax_finalized_at: datetime | None
    tax_finalized_by: str | None
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    related_invoice_id: int | None
    notes: str | None
    lines: list[InvoiceLineOut] = Field(default_factory=list)

class ApprovalDecision(BaseModel):
    comment: str | None = None

class TaxDeterminationCreate(BaseModel):
    tax_type: str = Field(pattern="^(withholding|vat|gst|other)$")
    jurisdiction: str = Field(min_length=1, max_length=100)
    rate: Decimal = Field(ge=0, le=100)
    taxable_amount: Decimal = Field(ge=0)
    tax_amount: Decimal = Field(ge=0)
    treaty_rate_id: int | None = None
    determined_by: str = Field(min_length=1, max_length=200)
    effective_date: date | None = None
    review_status: str = Field(default="pending", pattern="^(pending|reviewed|finalized)$")
    reviewer: str | None = None
    evidence_reference: str | None = None
    notes: str | None = None

class TaxDeterminationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tax_type: str
    jurisdiction: str
    rate: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    treaty_rate_id: int | None
    determined_by: str
    effective_date: date | None
    review_status: str
    reviewer: str | None
    evidence_reference: str | None
    notes: str | None

class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    payment_date: date
    value_date: date | None = None
    external_reference: str | None = None
    method: str | None = None
    source_account_reference: str | None = None

class PaymentAllocationCreate(BaseModel):
    invoice_id: int
    allocated_amount: Decimal = Field(gt=0)
    allocation_date: date

class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount: Decimal
    currency: str
    payment_date: date
    value_date: date | None
    external_reference: str | None
    method: str | None
    source_account_reference: str | None
    status: str

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=200)
    organization_id: int

class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    admin_email: str = Field(min_length=3, max_length=320)
    admin_password: str = Field(min_length=16, max_length=200)
    admin_display_name: str = Field(min_length=1, max_length=200)
    bootstrap_token: str = Field(min_length=16, max_length=500)
