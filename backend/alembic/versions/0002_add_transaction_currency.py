"""Preserve original amounts and label existing transactions as USD.

Downgrade is intentionally blocked if currency metadata would be lost.
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column('transactions', sa.Column('currency', sa.String(3), nullable=False,
                                          server_default=sa.text("'USD'")))
    op.create_check_constraint('ck_transactions_currency', 'transactions',
                               "currency IN ('USD', 'INR', 'AED')")


def downgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    incompatible = op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM transactions WHERE currency IS DISTINCT FROM 'USD')"
    ))
    if incompatible:
        raise RuntimeError('Downgrade refused: non-USD currency information would be lost. '
                           'No currency values or transaction amounts have been changed.')
    op.drop_constraint('ck_transactions_currency', 'transactions', type_='check')
    op.drop_column('transactions', 'currency')
