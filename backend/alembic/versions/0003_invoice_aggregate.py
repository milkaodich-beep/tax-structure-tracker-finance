from alembic import op
import sqlalchemy as sa

revision = '0003_invoice_aggregate'
down_revision = '0002_transaction_lifecycle'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('transaction_id', sa.Integer(), sa.ForeignKey('intercompany_transactions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('invoice_number', sa.String(50), nullable=False),
        sa.Column('invoice_type', sa.String(20), nullable=False, server_default='standard'),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('issue_date', sa.Date()),
        sa.Column('due_date', sa.Date()),
        sa.Column('subtotal_amount', sa.Numeric(20, 4), nullable=False),
        sa.Column('tax_amount', sa.Numeric(20, 4), nullable=False, server_default='0'),
        sa.Column('total_amount', sa.Numeric(20, 4), nullable=False),
        sa.Column('related_invoice_id', sa.Integer(), sa.ForeignKey('invoices.id', ondelete='RESTRICT')),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('invoice_number', name='uq_invoice_number'),
        sa.CheckConstraint('total_amount = subtotal_amount + tax_amount', name='ck_invoice_total'),
        sa.CheckConstraint('subtotal_amount >= 0', name='ck_invoice_subtotal_nonneg'),
        sa.CheckConstraint('tax_amount >= 0', name='ck_invoice_tax_nonneg'),
        sa.CheckConstraint("invoice_type IN ('standard','credit_note','debit_note')", name='ck_invoice_type'),
        sa.CheckConstraint("(invoice_type = 'standard') OR (related_invoice_id IS NOT NULL)", name='ck_invoice_credit_debit_requires_related'),
    )
    op.create_index('ix_invoices_transaction_id', 'invoices', ['transaction_id'])
    op.create_index('ix_invoices_invoice_number', 'invoices', ['invoice_number'])
    op.create_index('ix_invoices_status', 'invoices', ['status'])
    op.create_index('ix_invoices_created_at', 'invoices', ['created_at'])
    op.create_table(
        'invoice_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 4), nullable=False),
        sa.Column('unit_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('line_total', sa.Numeric(20, 4), nullable=False),
        sa.UniqueConstraint('invoice_id', 'line_number', name='uq_invoice_line_number'),
        sa.CheckConstraint('quantity > 0', name='ck_invoice_line_quantity_positive'),
        sa.CheckConstraint('unit_price >= 0', name='ck_invoice_line_unit_price_nonneg'),
        sa.CheckConstraint('line_total >= 0', name='ck_invoice_line_total_nonneg'),
    )
    op.create_index('ix_invoice_lines_invoice_id', 'invoice_lines', ['invoice_id'])
    op.create_table(
        'tax_determinations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tax_type', sa.String(20), nullable=False),
        sa.Column('jurisdiction', sa.String(100), nullable=False),
        sa.Column('rate', sa.Numeric(7, 4), nullable=False),
        sa.Column('taxable_amount', sa.Numeric(20, 4), nullable=False),
        sa.Column('tax_amount', sa.Numeric(20, 4), nullable=False),
        sa.Column('treaty_rate_id', sa.Integer(), sa.ForeignKey('treaty_rates.id', ondelete='SET NULL')),
        sa.Column('determined_by', sa.String(200), nullable=False),
        sa.Column('determined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('notes', sa.Text()),
        sa.CheckConstraint("tax_type IN ('withholding','vat','gst','other')", name='ck_tax_determination_type'),
        sa.CheckConstraint('taxable_amount >= 0', name='ck_tax_determination_taxable_nonneg'),
        sa.CheckConstraint('tax_amount >= 0', name='ck_tax_determination_amount_nonneg'),
    )
    op.create_index('ix_tax_determinations_invoice_id', 'tax_determinations', ['invoice_id'])
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Numeric(20, 4), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.Column('method', sa.String(50)),
        sa.Column('reference', sa.String(200)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('amount > 0', name='ck_payment_amount_positive'),
    )
    op.create_index('ix_payments_invoice_id', 'payments', ['invoice_id'])
    op.execute('CREATE SEQUENCE IF NOT EXISTS invoice_number_seq')


def downgrade():
    op.execute('DROP SEQUENCE IF EXISTS invoice_number_seq')
    op.drop_table('payments')
    op.drop_table('tax_determinations')
    op.drop_table('invoice_lines')
    op.drop_table('invoices')
