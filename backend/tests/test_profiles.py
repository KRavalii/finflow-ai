from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import database, financial_routes, financial_service, transactions
from app.database import Base
from app.main import app
from app.models import Profile, Transaction
from test_multicurrency import fake_rates


@pytest.fixture
def workspace(monkeypatch):
    engine = sa.create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @sa.event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, 'get_engine', lambda: engine)
    rates = fake_rates()
    for module in [transactions, financial_service, financial_routes]:
        monkeypatch.setattr(module, 'get_exchange_rates', lambda: rates)
    monkeypatch.setattr(financial_routes, 'reporting_today', lambda: date(2026, 11, 12))
    with TestClient(app) as client:
        yield client, engine, rates
    app.dependency_overrides.clear()
    engine.dispose()


def payload(profile_id=None, **changes):
    value = dict(description='Original', amount='12.34', currency='USD', category='Food',
                 transaction_type='expense', transaction_date='2026-10-10')
    if profile_id is not None:
        value['profile_id'] = profile_id
    return {**value, **changes}


def test_profile_lifecycle_and_default(workspace):
    client, engine, _ = workspace
    default = client.get('/api/profiles').json()[0]
    assert default['name'] == 'My Profile' and default['is_default']
    for name in ['Mom', 'Dad', 'Brother', 'Friends']:
        assert client.post('/api/profiles', json={'name': name}).status_code == 201
    mom = client.get('/api/profiles').json()[1]
    assert client.patch(f"/api/profiles/{mom['id']}", json={'name': 'Mother'}).json()['name'] == 'Mother'
    assert client.patch(f"/api/profiles/{default['id']}", json={'archived': True}).status_code == 409
    assert client.patch(f"/api/profiles/{default['id']}", json={'name': 'Me'}).status_code == 200
    assert client.post('/api/transactions', json=payload()).json()['profile_id'] == default['id']
    for body in [{'name': ' '}, {'name': None}, {'is_default': True}]:
        assert client.post('/api/profiles', json=body).status_code == 422
    for body in [{}, {'name': None}, {'archived': None}]:
        assert client.patch(f"/api/profiles/{mom['id']}", json=body).status_code == 422


def test_transaction_isolation_and_write_scope(workspace):
    client, _, _ = workspace
    mom = client.post('/api/profiles', json={'name': 'Mom'}).json()['id']
    mine = client.post('/api/transactions', json=payload()).json()
    theirs = client.post('/api/transactions', json=payload(mom)).json()
    assert [row['id'] for row in client.get('/api/transactions').json()] == [mine['id']]
    assert [row['id'] for row in client.get(f'/api/transactions?profile_id={mom}').json()] == [theirs['id']]
    assert len(client.get('/api/transactions?profile_id=all').json()) == 2
    path = f"/api/transactions/{theirs['id']}"
    for method, kwargs in [('get', {}), ('put', {'json': payload()}), ('delete', {})]:
        assert client.request(method, path, **kwargs).status_code == 404
    assert client.get(f'{path}?profile_id={mom}').json()['profile_name'] == 'Mom'
    assert client.put(f'{path}?profile_id={mom}', json=payload(mom, amount='20.00')).status_code == 200
    assert client.put(f'{path}?profile_id={mom}', json=payload(mine['profile_id'])).status_code == 409
    assert client.delete(f'{path}?profile_id=all').status_code == 422
    assert client.post('/api/transactions', json=payload('all')).status_code == 422
    assert client.get('/api/transactions?profile_id=99999').status_code == 404
    assert client.delete(f'{path}?profile_id={mom}').status_code == 204


def test_archiving_preserves_originals_and_combined_history(workspace):
    client, engine, _ = workspace
    mom = client.post('/api/profiles', json={'name': 'Mom'}).json()['id']
    original = client.post('/api/transactions', json=payload(mom)).json()
    assert client.patch(f'/api/profiles/{mom}', json={'archived': True}).status_code == 200
    assert len(client.get('/api/profiles').json()) == 1
    assert len(client.get('/api/profiles?include_archived=true').json()) == 2
    assert client.get(f'/api/transactions?profile_id={mom}').json()[0] == original
    assert client.get('/api/summary?profile_id=all').json()['expenses'] == '12.34'
    path = f"/api/transactions/{original['id']}?profile_id={mom}"
    assert client.post('/api/transactions', json=payload(mom)).status_code == 409
    assert client.put(path, json=payload(mom)).status_code == 409
    assert client.delete(path).status_code == 409
    with Session(engine) as db:
        with pytest.raises(sa.exc.IntegrityError):
            db.execute(sa.delete(Profile).where(Profile.id == mom))
            db.commit()
        db.rollback()
        assert db.get(Transaction, original['id']).amount == Decimal('12.34')
    assert client.patch(f'/api/profiles/{mom}', json={'archived': False}).status_code == 200


@pytest.mark.parametrize('currency', ['USD', 'INR', 'AED'])
def test_reports_assistant_comparison_and_conversion_isolation(workspace, currency):
    client, _, rates = workspace
    mom = client.post('/api/profiles', json={'name': 'Mom'}).json()['id']
    client.post('/api/transactions', json=payload(amount='10.00'))
    client.post('/api/transactions', json=payload(mom, amount='800.00', currency='INR'))
    # A future non-identity conversion must fail only in Mom/all scopes.
    client.post('/api/transactions', json=payload(mom, currency='AED', transaction_date='2027-01-01'))
    mine = client.get(f'/api/summary?reporting_currency={currency}').json()
    expected = {'USD': '10.00', 'INR': '800.00', 'AED': '36.73'}[currency]
    assert mine['expenses'] == expected and mine['transaction_count'] == 1
    assert mine['insights']['month_over_month']['current_expenses'] == expected
    assert mine['insights']['month_over_month']['current_transaction_count'] == 1
    assert mine['monthly_trends'][0]['expenses'] == expected
    answer = client.post('/api/assistant/query', json={'query': 'Summarize my finances', 'reporting_currency': currency}).json()
    assert answer['summary']['expenses'] == expected
    assert 'Profile: My Profile.' in answer['message']
    mom_report = client.get(f'/api/summary?profile_id={mom}&reporting_currency={currency}&end_date=2026-10-31').json()
    assert mom_report['expenses'] == expected and mom_report['profile_name'] == 'Mom'
    all_report = client.get(f'/api/summary?profile_id=all&reporting_currency={currency}&end_date=2026-10-31').json()
    assert Decimal(all_report['expenses']) == Decimal(expected) * 2
    if currency != 'AED':
        assert client.get(f'/api/summary?profile_id={mom}&reporting_currency={currency}').status_code == 503
    assert all(key[2] != date(2027, 1, 1) for key in rates.cache)


def test_pre_migration_compatibility_fails_closed(workspace):
    client, engine, _ = workspace
    # A separate schema stands in for an installation still at 0002.
    from app.models import CurrencyBase
    legacy = sa.create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    CurrencyBase.metadata.create_all(legacy)
    from app.database import get_db
    def get_legacy_db():
        with Session(legacy) as db:
            yield db
    app.dependency_overrides[get_db] = get_legacy_db
    try:
        # SQLite capability detection must inspect columns too.
        assert client.get('/api/profiles').status_code == 409
        assert client.get('/api/summary?profile_id=all').status_code == 409
        assert client.post('/api/transactions', json=payload(1)).status_code == 409
        assert client.post('/api/transactions', json=payload()).status_code == 201
        assert client.get('/api/summary').json()['expenses'] == '12.34'
    finally:
        app.dependency_overrides.clear()
        legacy.dispose()
