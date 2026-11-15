from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, func, select, text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from sqlalchemy.orm import DeclarativeBase


class TransactionFields:
    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    category: Mapped[str] = mapped_column(String(100))
    transaction_type: Mapped[str] = mapped_column(String(7))
    transaction_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Profile(Base):
    __tablename__ = 'profiles'
    __table_args__ = (
        CheckConstraint('length(trim(name)) > 0', name='ck_profiles_name_nonblank'),
        CheckConstraint('NOT is_default OR archived_at IS NULL', name='ck_profiles_default_active'),
        Index('uq_profiles_default', 'is_default', unique=True,
              postgresql_where=text('is_default'), sqlite_where=text('is_default')),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def default_profile_id(context):
    # ORM compatibility for callers that omit scope; never creates data on read.
    value = context.connection.scalar(select(Profile.id).where(Profile.is_default.is_(True)))
    if value is None:
        raise RuntimeError('Default profile is missing; migration 0003 must create it')
    return value


class Transaction(TransactionFields, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        CheckConstraint("transaction_type IN ('income', 'expense')", name="ck_transactions_type"),
        CheckConstraint("currency IN ('USD', 'INR', 'AED')", name='ck_transactions_currency'),
        Index('ix_transactions_profile_id_id', 'profile_id', 'id'),
        Index('ix_transactions_profile_id_date', 'profile_id', 'transaction_date'),
    )

    currency: Mapped[str] = mapped_column(String(3), server_default='USD')
    profile_id: Mapped[int] = mapped_column(ForeignKey('profiles.id', name='fk_transactions_profile', ondelete='RESTRICT'),
                                           default=default_profile_id)

    @property
    def profile_name(self):
        from sqlalchemy.orm import object_session
        profile = object_session(self).get(Profile, self.profile_id)
        return profile.name if profile else None


class LegacyBase(DeclarativeBase):
    pass


class LegacyTransaction(TransactionFields, LegacyBase):
    __tablename__ = 'transactions'

    @property
    def currency(self):
        return 'USD'


class CurrencyBase(DeclarativeBase):
    pass


class CurrencyTransaction(TransactionFields, CurrencyBase):
    """Read/write compatibility for installations awaiting approved 0003."""
    __tablename__ = 'transactions'
    currency: Mapped[str] = mapped_column(String(3), server_default='USD')
