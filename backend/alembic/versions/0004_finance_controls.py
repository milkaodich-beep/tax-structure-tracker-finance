"""Finance-grade invoice controls, audit metadata and payment allocation."""
from alembic import op
import sqlalchemy as sa

revision = "0004_finance_controls"
down_revision = "0003_invoice_aggregate"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("created_by_actor", sa.String(200), nullable=False, server_default="system"))
    op.add_column("invoices", sa.Column("accounting_date", sa.Date()))
    op.add_column("invoices", sa.Column("posting_date", sa.Date()))
    op.add_column("invoices", sa.Column("settled_date", sa.Date()))
    op.add_column("invoices", sa.Column("posted_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("approval_state", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("invoices", sa.Column("tax_finalized_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("tax_finalized_by", sa.String(200)))
    op.execute("UPDATE invoices SET approval_state='legacy' WHERE status IN ('issued','partially_paid','paid','void','credited')")
    op.drop_constraint("ck_invoice_status", "invoices", type_="check")
    op.execute("UPDATE invoices SET status='partially_settled' WHERE status='partially_paid'")
    op.execute("UPDATE invoices SET status='settled' WHERE status='paid'")
    op.execute("UPDATE invoices SET status='cancelled' WHERE status IN ('void','credited')")
    op.create_check_constraint("ck_invoice_status", "status IN ('draft','pending_approval','approved','issued','posted','partially_settled','settled','cancelled')", "invoices")

    op.add_column("tax_determinations", sa.Column("effective_date", sa.Date()))
    op.add_column("tax_determinations", sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("tax_determinations", sa.Column("reviewer", sa.String(200)))
    op.add_column("tax_determinations", sa.Column("evidence_reference", sa.Text()))
    op.create_check_constraint("ck_tax_determination_review_status", "review_status IN ('pending','reviewed','finalized')", "tax_determinations")

    op.add_column("payments", sa.Column("value_date", sa.Date()))
    op.add_column("payments", sa.Column("external_reference", sa.String(200)))
    op.add_column("payments", sa.Column("source_account_reference", sa.String(200)))
    op.add_column("payments", sa.Column("status", sa.String(20), nullable=False, server_default="received"))
    op.create_unique_constraint("uq_payment_external_reference", "payments", ["external_reference"])
    op.create_check_constraint("ck_payment_status", "status IN ('received','reconciled','reversed')", "payments")
    op.execute("UPDATE invoices SET currency=upper(currency)")
    op.execute("UPDATE payments SET currency=upper(currency)")
    op.create_check_constraint("ck_payment_currency", "currency = upper(currency) AND char_length(currency) = 3", "payments")
    op.create_check_constraint("ck_invoice_currency", "currency = upper(currency) AND char_length(currency) = 3", "invoices")
    op.create_check_constraint("ck_invoice_line_total_matches", "round(quantity * unit_price, 4) = line_total", "invoice_lines")

    op.create_table(
        "invoice_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.UniqueConstraint("invoice_id", "sequence", name="uq_invoice_approval_sequence"),
        sa.CheckConstraint("decision IN ('pending','approved','rejected')", name="ck_invoice_approval_decision"),
    )
    op.create_index("ix_invoice_approvals_invoice_id", "invoice_approvals", ["invoice_id"])

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("allocation_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("payment_id", "invoice_id", name="uq_payment_invoice_allocation"),
        sa.CheckConstraint("allocated_amount > 0", name="ck_payment_allocation_positive"),
        sa.CheckConstraint("status IN ('active','reversed')", name="ck_payment_allocation_status"),
    )
    op.create_index("ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"])
    op.create_index("ix_payment_allocations_invoice_id", "payment_allocations", ["invoice_id"])

    op.execute("""
        INSERT INTO payment_allocations (payment_id, invoice_id, allocated_amount, allocation_date, status)
        SELECT id, invoice_id, amount, payment_date, 'active'
        FROM payments
        WHERE invoice_id IS NOT NULL
    """)
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_constraint("payments_invoice_id_fkey", "payments", type_="foreignkey")
    op.drop_column("payments", "invoice_id")


def downgrade():
    op.add_column("payments", sa.Column("invoice_id", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE payments p SET invoice_id = a.invoice_id
        FROM payment_allocations a
        WHERE a.payment_id = p.id AND a.status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM payment_allocations a2
              WHERE a2.payment_id = p.id AND a2.status = 'active' AND a2.id <> a.id
          )
    """)
    op.create_foreign_key("payments_invoice_id_fkey", "payments", "invoices", ["invoice_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
    op.drop_table("payment_allocations")
    op.drop_table("invoice_approvals")
    op.drop_constraint("ck_invoice_line_total_matches", "invoice_lines", type_="check")
    op.drop_constraint("ck_invoice_currency", "invoices", type_="check")
    op.drop_constraint("ck_payment_currency", "payments", type_="check")
    op.drop_constraint("ck_payment_status", "payments", type_="check")
    op.drop_constraint("uq_payment_external_reference", "payments", type_="unique")
    for c in ["value_date", "external_reference", "source_account_reference", "status"]:
        op.drop_column("payments", c)
    op.drop_constraint("ck_tax_determination_review_status", "tax_determinations", type_="check")
    for c in ["effective_date", "review_status", "reviewer", "evidence_reference"]:
        op.drop_column("tax_determinations", c)
    op.drop_constraint("ck_invoice_status", "invoices", type_="check")
    op.execute("UPDATE invoices SET status='partially_paid' WHERE status='partially_settled'")
    op.execute("UPDATE invoices SET status='paid' WHERE status='settled'")
    op.execute("UPDATE invoices SET status='void' WHERE status='cancelled'")
    op.create_check_constraint("ck_invoice_status", "status IN ('draft','issued','partially_paid','paid','void','credited')", "invoices")
    for c in ["created_by_actor", "accounting_date", "posting_date", "settled_date", "posted_at", "approval_state", "tax_finalized_at", "tax_finalized_by"]:
        op.drop_column("invoices", c)
