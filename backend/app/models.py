from datetime import date
from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(30), index=True)
    parent_entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"))
    ownership_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    incorporation_date: Mapped[date | None] = mapped_column(Date)
    tax_id: Mapped[str | None] = mapped_column(String(100))
    parent: Mapped["Entity | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Entity"]] = relationship(back_populates="parent")

class SubstanceRecord(Base):
    __tablename__ = "substance_records"
    __table_args__ = (UniqueConstraint("entity_id", "period", name="uq_substance_entity_period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    period: Mapped[date] = mapped_column(Date, index=True)
    local_employee_count: Mapped[int] = mapped_column(Integer, default=0)
    has_local_office: Mapped[bool] = mapped_column(Boolean, default=False)
    decision_evidence_notes: Mapped[str | None] = mapped_column(Text)
    entity: Mapped[Entity] = relationship()
    board_meetings: Mapped[list["BoardMeeting"]] = relationship(back_populates="substance_record", cascade="all, delete-orphan")

class BoardMeeting(Base):
    __tablename__ = "board_meetings"
    id: Mapped[int] = mapped_column(primary_key=True)
    substance_record_id: Mapped[int] = mapped_column(ForeignKey("substance_records.id", ondelete="CASCADE"), index=True)
    meeting_date: Mapped[date] = mapped_column(Date)
    location: Mapped[str] = mapped_column(String(200))
    attendee_ids: Mapped[list] = mapped_column(JSONB, default=list)
    substance_record: Mapped[SubstanceRecord] = relationship(back_populates="board_meetings")

class IntercompanyTransaction(Base):
    __tablename__ = "intercompany_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), index=True)
    to_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), index=True)
    type: Mapped[str] = mapped_column(String(30), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    currency: Mapped[str] = mapped_column(String(3))
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    stated_price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    benchmark_low: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    benchmark_high: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    tp_documentation_link: Mapped[str | None] = mapped_column(Text)
    lifecycle_stage: Mapped[str] = mapped_column(String(20), default="pricing", server_default="pricing", index=True)
    invoice_reference: Mapped[str | None] = mapped_column(String(100))
    tax_treatment_notes: Mapped[str | None] = mapped_column(Text)
    settled_date: Mapped[date | None] = mapped_column(Date)
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="transaction")

class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_invoice_number"),
        CheckConstraint("total_amount = subtotal_amount + tax_amount", name="ck_invoice_total"),
        CheckConstraint("subtotal_amount >= 0", name="ck_invoice_subtotal_nonneg"),
        CheckConstraint("tax_amount >= 0", name="ck_invoice_tax_nonneg"),
        CheckConstraint("invoice_type IN ('standard','credit_note','debit_note')", name="ck_invoice_type"),
        CheckConstraint("status IN ('draft','pending_approval','approved','issued','posted','partially_settled','settled','cancelled')", name="ck_invoice_status"),
        CheckConstraint("currency = upper(currency) AND char_length(currency) = 3", name="ck_invoice_currency"),
        CheckConstraint("(invoice_type = 'standard') OR (related_invoice_id IS NOT NULL)", name="ck_invoice_credit_debit_requires_related"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_actor: Mapped[str] = mapped_column(String(200), default="system", server_default="system")
    transaction_id: Mapped[int] = mapped_column(ForeignKey("intercompany_transactions.id", ondelete="RESTRICT"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(50), index=True)
    invoice_type: Mapped[str] = mapped_column(String(20), default="standard", server_default="standard")
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(3))
    issue_date: Mapped[date | None] = mapped_column(Date)
    accounting_date: Mapped[date | None] = mapped_column(Date)
    posting_date: Mapped[date | None] = mapped_column(Date)
    settled_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    posted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    approval_state: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    tax_finalized_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    tax_finalized_by: Mapped[str | None] = mapped_column(String(200))
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0, server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    related_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    transaction: Mapped[IntercompanyTransaction] = relationship(back_populates="invoices")
    related_invoice: Mapped["Invoice | None"] = relationship(remote_side=[id])
    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.line_number")
    tax_determinations: Mapped[list["TaxDetermination"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    payments: Mapped[list["PaymentAllocation"]] = relationship("PaymentAllocation", back_populates="invoice")

class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint("invoice_id", "line_number", name="uq_invoice_line_number"),
        CheckConstraint("quantity > 0", name="ck_invoice_line_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_line_unit_price_nonneg"),
        CheckConstraint("line_total >= 0", name="ck_invoice_line_total_nonneg"),
        CheckConstraint("round(quantity * unit_price, 4) = line_total", name="ck_invoice_line_total_matches"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    line_total: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    invoice: Mapped[Invoice] = relationship(back_populates="lines")

class TaxDetermination(Base):
    __tablename__ = "tax_determinations"
    __table_args__ = (
        CheckConstraint("tax_type IN ('withholding','vat','gst','other')", name="ck_tax_determination_type"),
        CheckConstraint("taxable_amount >= 0", name="ck_tax_determination_taxable_nonneg"),
        CheckConstraint("tax_amount >= 0", name="ck_tax_determination_amount_nonneg"),
        CheckConstraint("review_status IN ('pending','reviewed','finalized')", name="ck_tax_determination_review_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    tax_type: Mapped[str] = mapped_column(String(20))
    jurisdiction: Mapped[str] = mapped_column(String(100))
    rate: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    treaty_rate_id: Mapped[int | None] = mapped_column(ForeignKey("treaty_rates.id", ondelete="SET NULL"))
    determined_by: Mapped[str] = mapped_column(String(200))
    determined_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    effective_date: Mapped[date | None] = mapped_column(Date)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    reviewer: Mapped[str | None] = mapped_column(String(200))
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    invoice: Mapped[Invoice] = relationship(back_populates="tax_determinations")

class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        CheckConstraint("currency = upper(currency) AND char_length(currency) = 3", name="ck_payment_currency"),
        CheckConstraint("status IN ('received','reconciled','reversed')", name="ck_payment_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    currency: Mapped[str] = mapped_column(String(3))
    payment_date: Mapped[date] = mapped_column(Date)
    value_date: Mapped[date | None] = mapped_column(Date)
    external_reference: Mapped[str | None] = mapped_column(String(200), unique=True)
    method: Mapped[str | None] = mapped_column(String(50))
    source_account_reference: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="received", server_default="received", index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    allocations: Mapped[list["PaymentAllocation"]] = relationship(back_populates="payment", cascade="all, delete-orphan")

class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        CheckConstraint("allocated_amount > 0", name="ck_payment_allocation_positive"),
        CheckConstraint("status IN ('active','reversed')", name="ck_payment_allocation_status"),
        UniqueConstraint("payment_id", "invoice_id", name="uq_payment_invoice_allocation"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), index=True)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    allocation_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    payment: Mapped[Payment] = relationship(back_populates="allocations")
    invoice: Mapped[Invoice] = relationship(back_populates="payments")

class ApprovalRecord(Base):
    __tablename__ = "invoice_approvals"
    __table_args__ = (
        CheckConstraint("decision IN ('pending','approved','rejected')", name="ck_invoice_approval_decision"),
        UniqueConstraint("invoice_id", "sequence", name="uq_invoice_approval_sequence"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(200))
    decided_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    comment: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer)

class TreatyRate(Base):
    __tablename__ = "treaty_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_from: Mapped[str] = mapped_column(String(100), index=True)
    country_to: Mapped[str] = mapped_column(String(100), index=True)
    income_type: Mapped[str] = mapped_column(String(30))
    withholding_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    treaty_source_url: Mapped[str] = mapped_column(Text)
    last_verified_date: Mapped[date] = mapped_column(Date, index=True)

class PillarTwoStatus(Base):
    __tablename__ = "pillar_two_status"
    __table_args__ = (UniqueConstraint("entity_id", "period", name="uq_pillar_entity_period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(100), index=True)
    period: Mapped[date] = mapped_column(Date, index=True)
    globe_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    covered_taxes: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    effective_tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    qdmtt_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    safe_harbour_type: Mapped[str | None] = mapped_column(String(50))
    gir_filing_deadline: Mapped[date | None] = mapped_column(Date)
    gir_filed: Mapped[bool] = mapped_column(Boolean, default=False)
    entity: Mapped[Entity] = relationship()

class ComplianceCalendar(Base):
    __tablename__ = "compliance_calendar"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    obligation_type: Mapped[str] = mapped_column(String(100), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(100), index=True)
    deadline: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    entity: Mapped[Entity] = relationship()

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100))
    object_type: Mapped[str] = mapped_column(String(100))
    object_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
