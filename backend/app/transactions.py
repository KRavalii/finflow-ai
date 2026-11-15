from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Transaction, LegacyTransaction
from .transaction_storage import transaction_model
from .currencies import Currency, RatePolicy
from .exchange_rates import get_exchange_rates, RatesUnavailable
import time
from .schemas import TransactionRead, TransactionWrite
from .profile_scope import ProfileScope, resolve_profile, scope_statement

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
Database = Annotated[Session, Depends(get_db)]
TransactionId = Annotated[int, Path(gt=0)]


def find_transaction(db: Session, transaction_id: int, profile_id: ProfileScope = None, *, write=False) -> Transaction:
    if profile_id == 'all':
        raise HTTPException(422, 'Select one profile to access an individual transaction')
    profile = resolve_profile(db, profile_id, write=write)
    model = transaction_model(db)
    transaction = db.scalar(scope_statement(select(model).where(model.id == transaction_id), model, profile))
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


@router.post("", response_model=TransactionRead, status_code=201)
def create_transaction(payload: TransactionWrite, db: Database):
    profile = resolve_profile(db, payload.profile_id, write=True)
    model = transaction_model(db)
    values = payload.model_dump(exclude={'profile_id'})
    if profile is not None:
        values['profile_id'] = profile.id
    if model is LegacyTransaction:
        if values.pop('currency') != 'USD':
            raise HTTPException(409, 'Saving non-USD transactions requires approved migration 0002; the database has not been changed')
    transaction = model(**values)
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.get("", response_model=list[TransactionRead])
def list_transactions(db: Database, offset: Annotated[int, Query(ge=0)] = 0,
                      limit: Annotated[int, Query(ge=1, le=100)] = 50,
                      reporting_currency: Currency | None = None, rate_policy: RatePolicy = 'historical', profile_id: ProfileScope = None):
    model = transaction_model(db)
    profile = resolve_profile(db, profile_id)
    rows = db.scalars(scope_statement(select(model), model, profile).order_by(model.id).offset(offset).limit(limit)).all()
    if reporting_currency is None:
        return rows
    rates = get_exchange_rates()
    deadline = time.monotonic() + 12
    result = []
    for row in rows:
        value = TransactionRead.model_validate(row)
        value.reporting_currency = reporting_currency
        try:
            converted, evidence = rates.convert(row.amount, row.currency, reporting_currency, row.transaction_date, rate_policy, deadline)
            value.converted_amount = format(converted, '.2f')
            value.conversion = evidence
        except RatesUnavailable as error:
            value.conversion_error = error.detail
        result.append(value)
    return result


@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(transaction_id: TransactionId, db: Database, profile_id: ProfileScope = None):
    return find_transaction(db, transaction_id, profile_id)


@router.put("/{transaction_id}", response_model=TransactionRead)
def update_transaction(transaction_id: TransactionId, payload: TransactionWrite, db: Database, profile_id: ProfileScope = None):
    transaction = find_transaction(db, transaction_id, profile_id, write=True)
    if payload.profile_id is not None and payload.profile_id != getattr(transaction, 'profile_id', None):
        raise HTTPException(409, 'Moving transactions between profiles is not supported')
    values = payload.model_dump(exclude={'profile_id'})
    if 'currency' not in payload.model_fields_set:
        values.pop('currency')
    if isinstance(transaction, LegacyTransaction):
        if values.pop('currency', 'USD') != 'USD':
            raise HTTPException(409, 'Saving non-USD transactions requires approved migration 0002; the database has not been changed')
    for key, value in values.items():
        setattr(transaction, key, value)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: TransactionId, db: Database, profile_id: ProfileScope = None):
    db.delete(find_transaction(db, transaction_id, profile_id, write=True))
    db.commit()
    return Response(status_code=204)
