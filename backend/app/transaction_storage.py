"""Compatibility while production intentionally remains at Alembic 0001."""
from sqlalchemy import inspect
from .models import CurrencyTransaction, LegacyTransaction, Transaction


def transaction_model(db):
    if 'transaction_model' not in db.info:
        columns = {column['name'] for column in inspect(db.connection()).get_columns('transactions')}
        db.info['transaction_model'] = (Transaction if 'profile_id' in columns else
                                        CurrencyTransaction if 'currency' in columns else LegacyTransaction)
    return db.info['transaction_model']
