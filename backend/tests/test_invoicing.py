from decimal import Decimal
import pytest
from app.invoicing import FinanceError, create_invoice, submit_invoice, approve_invoice, finalize_tax, issue_invoice, post_invoice

@pytest.mark.asyncio
async def test_maker_checker_and_posting_boundary(db):
    invoice = await create_invoice(db, organization_id=1, transaction_id=1, actor="maker", invoice_type="standard", currency="USD",
        issue_date=None, due_date=None, related_invoice_id=None, notes=None,
        lines=[{"description":"Service","quantity":Decimal("2"),"unit_price":Decimal("50")}])
    assert invoice.total_amount == Decimal("100.0000")
    await submit_invoice(db, invoice.id, "maker", organization_id=1)
    with pytest.raises(FinanceError): await approve_invoice(db, invoice.id, "maker", organization_id=1)
    await approve_invoice(db, invoice.id, "checker", organization_id=1)
    await finalize_tax(db, invoice.id, "tax", [{
        "tax_type":"other","jurisdiction":"KE","rate":Decimal("0"),
        "taxable_amount":Decimal("100"),"tax_amount":Decimal("0"),
        "treaty_rate_id":None,"determined_by":"tax"
    }], organization_id=1)
    await issue_invoice(db, invoice.id, "issuer", organization_id=1)
    await post_invoice(db, invoice.id, "poster", organization_id=1)
    with pytest.raises(FinanceError): await submit_invoice(db, invoice.id, "maker")
