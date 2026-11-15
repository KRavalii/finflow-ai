"""Opt-in real PostgreSQL application tests; every mutation is rolled back."""
from decimal import Decimal

from alembic import command
from fastapi.testclient import TestClient
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app import financial_routes, financial_service, transactions
from app.database import get_db
from app.main import app
from test_currency_migration import isolated_migration, existing_rows
from test_multicurrency import fake_rates


def test_postgres_currency_crud_reports_and_assistant(isolated_migration, monkeypatch):
    connection, config, original = isolated_migration
    command.upgrade(config, '0002')
    # A transactional test-only constant default avoids advancing the serial
    # sequence (sequence increments cannot be rolled back in PostgreSQL).
    fixture_id = max(row['id'] for row in original) + 1000
    assert fixture_id < 2147483647
    connection.execute(sa.text(f'ALTER TABLE transactions ALTER COLUMN id SET DEFAULT {int(fixture_id)}'))
    rates = fake_rates()
    for module in [transactions, financial_service, financial_routes]:
        monkeypatch.setattr(module, 'get_exchange_rates', lambda: rates)

    def isolated_session():
        with Session(bind=connection, join_transaction_mode='create_savepoint') as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = isolated_session
    try:
        with TestClient(app) as client:
            payload = {'description':'Isolated currency verification','amount':'123.45','currency':'INR',
                       'category':'Verification','transaction_type':'expense','transaction_date':'2026-10-10'}
            response = client.post('/api/transactions', json=payload)
            assert response.status_code == 201
            assert response.json()['id'] == fixture_id
            path = f'/api/transactions/{fixture_id}'
            assert client.get(path).json()['currency'] == 'INR'
            replacement = {key:value for key,value in payload.items() if key != 'currency'}
            replacement['amount'] = '456.78'
            response = client.put(path, json=replacement)
            assert response.status_code == 200
            assert (response.json()['amount'], response.json()['currency']) == ('456.78','INR')
            for currency in ['USD','INR','AED']:
                options = {'reporting_currency':currency, 'rate_policy':'latest'}
                listed = client.get('/api/transactions', params=options)
                assert listed.status_code == 200
                income = sum((Decimal(item['converted_amount']) for item in listed.json() if item['transaction_type']=='income'),Decimal('0'))
                expenses = sum((Decimal(item['converted_amount']) for item in listed.json() if item['transaction_type']=='expense'),Decimal('0'))
                report = client.get('/api/summary', params=options)
                assert report.status_code == 200
                summary = report.json()
                assert Decimal(summary['income']) == income and Decimal(summary['expenses']) == expenses
                assert Decimal(summary['net_balance']) == income-expenses
                answer = client.post('/api/assistant/query', json={'query':'summarise my finances',**options})
                assert answer.status_code == 200
                assert answer.json()['summary']['net_balance'] == summary['net_balance']
                assert answer.json()['summary']['spending_by_category'] == summary['spending_by_category']
                assert answer.json()['summary']['monthly_trends'] == summary['monthly_trends']
            assert client.delete(path).status_code == 204
            assert client.get(path).status_code == 404
            assert existing_rows(connection) == original
    finally:
        app.dependency_overrides.clear()
    # The outer fixture rolls back schema, test defaults, data and revision.
