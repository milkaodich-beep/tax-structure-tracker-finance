"""Allow reallocation of a payment to an invoice after a prior allocation is reversed."""
from alembic import op

revision = "0005_payment_allocation_reuse"
down_revision = "0004_finance_controls"
branch_labels = None
depends_on = None

def upgrade():
    op.drop_constraint("uq_payment_invoice_allocation", "payment_allocations", type_="unique")
    op.create_index("ix_payment_allocations_payment_invoice_status", "payment_allocations", ["payment_id", "invoice_id", "status"])

def downgrade():
    op.drop_index("ix_payment_allocations_payment_invoice_status", table_name="payment_allocations")
    op.create_unique_constraint("uq_payment_invoice_allocation", "payment_allocations", ["payment_id", "invoice_id"])
