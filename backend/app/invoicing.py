from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from .audit import record_audit
from .models import ApprovalRecord, Invoice, InvoiceLine, Payment, PaymentAllocation, TaxDetermination

LIFECYCLE = {
    "draft": {"pending_approval", "cancelled"},
    "pending_approval": {"approved", "draft", "cancelled"},
    "approved": {"issued", "pending_approval"},
    "issued": {"posted"},
    "posted": {"partially_settled", "settled"},
    "partially_settled": {"settled", "posted"},
    "settled": set(),
    "cancelled": set(),
}
Q4 = Decimal("0.0001")

class FinanceError(ValueError): pass

def _q(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)

async def get_invoice(db: AsyncSession, invoice_id: int, *, lock: bool = False) -> Invoice:
    stmt = select(Invoice).options(selectinload(Invoice.lines), selectinload(Invoice.tax_determinations))
    if lock:
        stmt = stmt.with_for_update()
    invoice = await db.scalar(stmt.where(Invoice.id == invoice_id))
    if not invoice:
        raise FinanceError("Invoice not found")
    return invoice

def _assert_mutable(invoice: Invoice) -> None:
    if invoice.status in {"issued", "posted", "partially_settled", "settled"}:
        raise FinanceError("Posted/issued financial documents cannot be mutated directly")

async def create_invoice(db: AsyncSession, *, transaction_id: int, actor: str, invoice_type: str, currency: str,
                          issue_date: date | None, due_date: date | None, related_invoice_id: int | None,
                          notes: str | None, lines: list[dict], correlation_id: str | None = None) -> Invoice:
    currency = currency.upper()
    if invoice_type in {"credit_note", "debit_note"}:
        if related_invoice_id is None:
            raise FinanceError("Adjustment invoice requires a related invoice")
        related = await get_invoice(db, related_invoice_id)
        if related.status == "cancelled":
            raise FinanceError("Cannot adjust a cancelled invoice")
    if issue_date and due_date and due_date < issue_date:
        raise FinanceError("Due date cannot be before issue date")
    invoice = Invoice(transaction_id=transaction_id, invoice_number=f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
                      invoice_type=invoice_type, currency=currency, issue_date=issue_date, due_date=due_date,
                      related_invoice_id=related_invoice_id, notes=notes, created_by_actor=actor,
                      subtotal_amount=Decimal("0"), tax_amount=Decimal("0"), total_amount=Decimal("0"))
    db.add(invoice)
    await db.flush()
    subtotal = Decimal("0")
    for i, item in enumerate(lines, 1):
        qty = Decimal(str(item["quantity"])); price = Decimal(str(item["unit_price"]))
        total = _q(qty * price); subtotal += total
        db.add(InvoiceLine(invoice_id=invoice.id, line_number=i, description=item["description"],
                           quantity=qty, unit_price=price, line_total=total))
    invoice.subtotal_amount = _q(subtotal)
    invoice.total_amount = invoice.subtotal_amount
    await record_audit(db, actor=actor, action="invoice.created", object_type="invoice",
                       object_id=invoice.id, new_state=invoice.status, changes={"total": str(invoice.total_amount)},
                       correlation_id=correlation_id)
    return invoice

async def submit_invoice(db: AsyncSession, invoice_id: int, actor: str, correlation_id: str | None = None) -> Invoice:
    invoice = await get_invoice(db, invoice_id, lock=True)
    _assert_mutable(invoice)
    if invoice.status != "draft": raise FinanceError("Only draft invoices can be submitted")
    invoice.status = "pending_approval"; invoice.approval_state = "pending"
    await record_audit(db, actor=actor, action="invoice.submitted", object_type="invoice", object_id=invoice.id,
                       previous_state="draft", new_state=invoice.status, correlation_id=correlation_id)
    return invoice

async def approve_invoice(db: AsyncSession, invoice_id: int, actor: str, comment: str | None = None, correlation_id: str | None = None) -> Invoice:
    invoice = await get_invoice(db, invoice_id, lock=True)
    if invoice.status != "pending_approval": raise FinanceError("Invoice is not awaiting approval")
    if actor == invoice.created_by_actor: raise FinanceError("Maker cannot approve their own invoice")
    last = await db.scalar(select(func.max(ApprovalRecord.sequence)).where(ApprovalRecord.invoice_id == invoice.id))
    db.add(ApprovalRecord(invoice_id=invoice.id, decision="approved", actor=actor, comment=comment, sequence=(last or 0)+1))
    invoice.status = "approved"; invoice.approval_state = "approved"
    await record_audit(db, actor=actor, action="invoice.approved", object_type="invoice", object_id=invoice.id,
                       previous_state="pending_approval", new_state="approved", changes={"comment": comment}, correlation_id=correlation_id)
    return invoice

async def reject_invoice(db: AsyncSession, invoice_id: int, actor: str, comment: str | None = None, correlation_id: str | None = None) -> Invoice:
    invoice = await get_invoice(db, invoice_id, lock=True)
    if invoice.status != "pending_approval": raise FinanceError("Invoice is not awaiting approval")
    last = await db.scalar(select(func.max(ApprovalRecord.sequence)).where(ApprovalRecord.invoice_id == invoice.id))
    db.add(ApprovalRecord(invoice_id=invoice.id, decision="rejected", actor=actor, comment=comment, sequence=(last or 0)+1))
    invoice.status = "draft"; invoice.approval_state = "rejected"
    await record_audit(db, actor=actor, action="invoice.rejected", object_type="invoice", object_id=invoice.id,
                       previous_state="pending_approval", new_state="draft", changes={"comment": comment}, correlation_id=correlation_id)
    return invoice

async def finalize_tax(db: AsyncSession, invoice_id: int, actor: str, determinations: list[dict], correlation_id: str | None = None) -> Invoice:
    invoice = await get_invoice(db, invoice_id, lock=True)
    _assert_mutable(invoice)
    if invoice.status not in {"draft", "pending_approval", "approved"}: raise FinanceError("Tax can only be finalized before issuance")
    total_tax = Decimal("0")
    for item in determinations:
        tax = Decimal(str(item["tax_amount"])); total_tax += tax
        db.add(TaxDetermination(invoice_id=invoice.id, **item, tax_amount=tax, review_status="finalized",
                                reviewer=actor))
    invoice.tax_amount = _q(total_tax); invoice.total_amount = _q(invoice.subtotal_amount + invoice.tax_amount)
    invoice.tax_finalized_at = datetime.now(timezone.utc); invoice.tax_finalized_by = actor
    await record_audit(db, actor=actor, action="tax.finalized", object_type="invoice", object_id=invoice.id,
                       changes={"tax_amount": str(invoice.tax_amount), "total": str(invoice.total_amount)}, correlation_id=correlation_id)
    return invoice

async def issue_invoice(db: AsyncSession, invoice_id: int, actor: str, correlation_id: str | None = None) -> Invoice:
    invoice = await get_invoice(db, invoice_id, lock=True)
    if invoice.status != "approved": raise FinanceError("Invoice must be approved before issuance")
    if not invoice.tax_finalized_at: raise FinanceError("Tax determination must be finalized before issuance")
    invoice.status = "issued"; invoice.issue_date = invoice.issue_date or date.today()
    await record_audit(db, actor=actor, action="invoice.issued", object_type="invoice", object_id=invoice.id,
                       previous_state="approved", new_state="issued", correlation_id=correlation_id)
    return invoice

async def post_invoice(db: AsyncSession, invoice_id: int, actor: str, accounting_date: date | None = None, correlation_id: str | None = None) -> Invoice:
    invoice = await get_invoice(db, invoice_id, lock=True)
    if invoice.status != "issued": raise FinanceError("Only issued invoices can be posted")
    invoice.status = "posted"; invoice.accounting_date = accounting_date or date.today()
    invoice.posting_date = date.today(); invoice.posted_at = datetime.now(timezone.utc)
    await record_audit(db, actor=actor, action="invoice.posted", object_type="invoice", object_id=invoice.id,
                       previous_state="issued", new_state="posted", correlation_id=correlation_id)
    return invoice

async def cancel_invoice(db: AsyncSession, invoice_id: int, actor: str, correlation_id: str | None = None) -> Invoice:
    invoice = await get_invoice(db, invoice_id, lock=True)
    if invoice.status not in {"draft", "pending_approval", "approved"}: raise FinanceError("Only pre-issuance invoices can be cancelled")
    old=invoice.status; invoice.status="cancelled"
    await record_audit(db, actor=actor, action="invoice.cancelled", object_type="invoice", object_id=invoice.id,
                       previous_state=old, new_state="cancelled", correlation_id=correlation_id)
    return invoice

async def create_payment(db: AsyncSession, *, actor: str, data: dict, correlation_id: str | None = None) -> Payment:
    data["currency"] = data["currency"].upper()
    payment = Payment(**data)
    db.add(payment); await db.flush()
    await record_audit(db, actor=actor, action="payment.created", object_type="payment", object_id=payment.id, correlation_id=correlation_id)
    return payment

async def allocate_payment(db: AsyncSession, payment_id: int, *, invoice_id: int, amount: Decimal, allocation_date: date, actor: str, correlation_id: str | None = None) -> PaymentAllocation:
    payment = await db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    invoice = await get_invoice(db, invoice_id, lock=True)
    if not payment or payment.status == "reversed": raise FinanceError("Payment unavailable")
    if invoice.status not in {"posted", "partially_settled"}: raise FinanceError("Only posted invoices can be settled")
    amount = _q(Decimal(str(amount)))
    if payment.currency != invoice.currency: raise FinanceError("Payment and invoice currencies must match")
    used = await db.scalar(select(func.coalesce(func.sum(PaymentAllocation.allocated_amount),0)).where(PaymentAllocation.payment_id==payment.id, PaymentAllocation.status=="active"))
    if _q((used or Decimal("0")) + amount) > payment.amount: raise FinanceError("Allocation exceeds payment amount")
    paid = await db.scalar(select(func.coalesce(func.sum(PaymentAllocation.allocated_amount),0)).where(PaymentAllocation.invoice_id==invoice.id, PaymentAllocation.status=="active"))
    if _q((paid or Decimal("0")) + amount) > invoice.total_amount: raise FinanceError("Allocation exceeds invoice balance")
    existing = await db.scalar(select(PaymentAllocation).where(PaymentAllocation.payment_id==payment.id, PaymentAllocation.invoice_id==invoice.id, PaymentAllocation.status=="active"))
    if existing:
        existing.allocated_amount = _q(existing.allocated_amount + amount); allocation = existing
    else:
        allocation = PaymentAllocation(payment_id=payment.id, invoice_id=invoice.id, allocated_amount=amount, allocation_date=allocation_date)
        db.add(allocation)
    new_paid = _q((paid or Decimal("0")) + amount)
    invoice.status = "settled" if new_paid == invoice.total_amount else "partially_settled"
    if invoice.status == "settled": invoice.settled_date = allocation_date
    payment.status = "reconciled" if _q((used or Decimal("0")) + amount) == payment.amount else "received"
    await record_audit(db, actor=actor, action="payment.allocated", object_type="payment", object_id=payment.id,
                       changes={"invoice_id": invoice.id, "amount": str(amount)}, correlation_id=correlation_id)
    return allocation

async def reverse_payment(db: AsyncSession, payment_id: int, actor: str, correlation_id: str | None = None) -> Payment:
    payment = await db.scalar(select(Payment).where(Payment.id==payment_id).with_for_update())
    if not payment: raise FinanceError("Payment not found")
    if payment.status == "reversed": raise FinanceError("Payment already reversed")
    allocations = (await db.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id==payment.id, PaymentAllocation.status=="active").with_for_update())).all()
    for allocation in allocations:
        invoice = await get_invoice(db, allocation.invoice_id, lock=True)
        allocation.status = "reversed"
        paid = await db.scalar(select(func.coalesce(func.sum(PaymentAllocation.allocated_amount),0)).where(PaymentAllocation.invoice_id==invoice.id, PaymentAllocation.status=="active"))
        invoice.status = "posted" if (paid or Decimal("0")) == 0 else "partially_settled"
        invoice.settled_date = None
    payment.status = "reversed"
    await record_audit(db, actor=actor, action="payment.reversed", object_type="payment", object_id=payment.id,
                       changes={"allocations_reversed": len(allocations)}, correlation_id=correlation_id)
    return payment
