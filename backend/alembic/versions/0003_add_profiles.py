"""Add profiles and associate existing transactions without altering originals."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    profiles = op.create_table(
        'profiles',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('length(trim(name)) > 0', name='ck_profiles_name_nonblank'),
        sa.CheckConstraint('NOT is_default OR archived_at IS NULL', name='ck_profiles_default_active'),
    )
    op.create_index('uq_profiles_default', 'profiles', ['is_default'], unique=True,
                    postgresql_where=sa.text('is_default'))
    default_id = op.get_bind().scalar(profiles.insert().values(name='My Profile', is_default=True).returning(profiles.c.id))
    op.add_column('transactions', sa.Column('profile_id', sa.Integer(), nullable=True))
    op.get_bind().execute(sa.text('UPDATE transactions SET profile_id = :profile_id'), {'profile_id': default_id})
    op.alter_column('transactions', 'profile_id', nullable=False)
    op.create_foreign_key('fk_transactions_profile', 'transactions', 'profiles', ['profile_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_transactions_profile_id_id', 'transactions', ['profile_id', 'id'])
    op.create_index('ix_transactions_profile_id_date', 'transactions', ['profile_id', 'transaction_date'])


def downgrade():
    raise RuntimeError('Downgrade refused: removing profiles would discard financial profile information.')
