from alembic import op
import sqlalchemy as sa

revision = '0002_transaction_lifecycle'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('intercompany_transactions', sa.Column('lifecycle_stage', sa.String(20), nullable=False, server_default='pricing'))
    op.add_column('intercompany_transactions', sa.Column('invoice_reference', sa.String(100)))
    op.add_column('intercompany_transactions', sa.Column('tax_treatment_notes', sa.Text()))
    op.add_column('intercompany_transactions', sa.Column('settled_date', sa.Date()))
    op.create_index('ix_ic_lifecycle_stage', 'intercompany_transactions', ['lifecycle_stage'])


def downgrade():
    op.drop_index('ix_ic_lifecycle_stage', table_name='intercompany_transactions')
    op.drop_column('intercompany_transactions', 'settled_date')
    op.drop_column('intercompany_transactions', 'tax_treatment_notes')
    op.drop_column('intercompany_transactions', 'invoice_reference')
    op.drop_column('intercompany_transactions', 'lifecycle_stage')
