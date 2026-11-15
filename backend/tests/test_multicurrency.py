from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import database, financial_routes, financial_service, transactions
from app.currencies import currency_money
from app.database import Base
from app.exchange_rates import ExchangeRates, RatesUnavailable
from app.main import app
from app.models import LegacyBase, LegacyTransaction, Transaction


def fake_rates():
    units = {'USD': Decimal('1'), 'INR': Decimal('80'), 'AED': Decimal('3.6725')}
    def respond(request):
        base, quote = request.url.path.split('/')[-2:]
        rate = units[quote.upper()] / units[base.upper()]
        return httpx.Response(200, json={'base': base.upper(), 'quote': quote.upper(),
            'date': request.url.params.get('date', '2026-11-12'), 'rate': str(rate)})
    return ExchangeRates(httpx.Client(transport=httpx.MockTransport(respond), base_url='https://api.frankfurter.dev'),
                         clock=lambda: date(2026, 11, 12))


@pytest.fixture
def currency_client(monkeypatch):
    engine = sa.create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    rates = fake_rates()
    monkeypatch.setattr(database, 'get_engine', lambda: engine)
    for module in [transactions, financial_service, financial_routes]:
        monkeypatch.setattr(module, 'get_exchange_rates', lambda: rates)
    monkeypatch.setattr(financial_routes, 'reporting_today', lambda: date(2026, 11, 12))
    with TestClient(app) as client:
        yield client, engine, rates
    app.dependency_overrides.clear()
    engine.dispose()


def add_mixed(engine):
    values = [('income', 'USD', '100.00'), ('income', 'INR', '8000.00'),
              ('expense', 'INR', '800.00'), ('expense', 'AED', '36.73')]
    with Session(engine) as db:
        db.add_all(Transaction(description='Private transaction', amount=Decimal(amount), currency=currency,
                  category='Work' if kind == 'income' else 'Food', transaction_type=kind,
                  transaction_date=date(2026, 10, 10)) for kind, currency, amount in values)
        db.commit()


@pytest.mark.parametrize('currency,income,expenses,balance', [
    ('USD', '200.00', '20.00', '180.00'), ('INR', '16000.00', '1600.11', '14399.89'),
    ('AED', '734.50', '73.46', '661.04'),
])
@pytest.mark.parametrize('policy', ['historical', 'latest'])
def test_summary_transactions_and_assistant_share_rounding(currency_client, currency, income, expenses, balance, policy):
    client, engine, _ = currency_client
    add_mixed(engine)
    options = {'reporting_currency': currency, 'rate_policy': policy}
    response = client.get('/api/summary', params=options)
    assert response.status_code == 200
    summary = response.json()
    assert (summary['income'], summary['expenses'], summary['net_balance']) == (income, expenses, balance)
    assert summary['spending_by_category'][0]['total'] == expenses
    assert summary['monthly_trends'][0]['net_balance'] == balance
    listed = client.get('/api/transactions', params=options).json()
    assert sum((Decimal(row['converted_amount']) for row in listed if row['transaction_type'] == 'income'), Decimal('0')) == Decimal(income)
    assert sum((Decimal(row['converted_amount']) for row in listed if row['transaction_type'] == 'expense'), Decimal('0')) == Decimal(expenses)
    answer = client.post('/api/assistant/query', json={'query': 'summarise my finances', **options}).json()
    # cache_hit/fetched_at are diagnostic metadata and can differ across requests.
    assert answer['summary']['income'] == income and answer['summary']['net_balance'] == balance
    assert f'Financial summary ({currency})' in answer['message']
    assert currency_money(Decimal(balance), currency) in answer['message']
    assert 'Reporting period:' in answer['message'] and 'Rate date(s):' in answer['message']
    with Session(engine) as db:
        assert [(row.currency, str(row.amount)) for row in db.scalars(sa.select(Transaction).order_by(Transaction.id))] == [('USD','100.00'),('INR','8000.00'),('INR','800.00'),('AED','36.73')]


def test_currency_crud_preserves_original_and_omitted_update(currency_client):
    client, _, _ = currency_client
    payload = {'description':'Currency test', 'amount':'123.45', 'category':'Test', 'transaction_type':'expense', 'transaction_date':'2026-10-10', 'currency':'INR'}
    response = client.post('/api/transactions', json=payload)
    assert response.status_code == 201
    row = response.json()
    assert row['currency'] == 'INR' and row['amount'] == '123.45'
    updated = client.put(f"/api/transactions/{row['id']}", json={k:v for k,v in payload.items() if k != 'currency'})
    assert updated.json()['currency'] == 'INR'
    assert client.post('/api/transactions', json={**payload,'currency':'EUR'}).status_code == 422
    assert client.get('/api/summary?reporting_currency=EUR').status_code == 422
    assert client.get('/api/summary?rate_policy=unsafe').status_code == 422
    assert client.post('/api/assistant/query', json={'query':'income','reporting_currency':'EUR'}).status_code == 422


@pytest.mark.parametrize('currency', ['USD','INR','AED'])
def test_salary_income_currency_payload_is_accepted_and_retrieved(currency_client, currency):
    client, engine, _ = currency_client
    payload = {'description':'Salary','amount':'300','category':'Salary','transaction_type':'income',
               'transaction_date':'2026-11-12','currency':currency}
    response = client.post('/api/transactions',json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created['currency'] == currency and created['amount'] == '300.00'
    retrieved = client.get('/api/transactions/'+str(created['id']))
    assert retrieved.status_code == 200 and retrieved.json() == created
    with Session(engine) as db:
        row = db.get(Transaction,created['id'])
        assert row.currency == currency and row.amount == Decimal('300.00')


def test_openapi_declares_currency_for_transaction_create_and_update(currency_client):
    client, _, _ = currency_client
    spec = client.get('/openapi.json').json()
    schema = spec['components']['schemas']['TransactionWrite']
    assert set(schema['properties']['currency']['enum']) == {'USD','INR','AED'}
    assert schema['additionalProperties'] is False
    for path,method in [('/api/transactions','post'),('/api/transactions/{transaction_id}','put')]:
        reference = spec['paths'][path][method]['requestBody']['content']['application/json']['schema']['$ref']
        assert reference == '#/components/schemas/TransactionWrite'


def test_missing_rates_hide_summary_but_preserve_original_list(currency_client, monkeypatch):
    client, engine, rates = currency_client
    add_mixed(engine)
    def fail(*args, **kwargs):
        raise RatesUnavailable('INR','USD',date(2026,10,10))
    monkeypatch.setattr(rates, 'convert', fail)
    assert client.get('/api/summary').status_code == 503
    assert client.post('/api/assistant/query', json={'query':'summarize my finances'}).status_code == 503
    rows = client.get('/api/transactions?reporting_currency=USD').json()
    assert len(rows) == 4 and all(row['converted_amount'] is None and row['conversion_error'] for row in rows)
    assert rows[0]['amount'] == '100.00'
    assert client.get('/api/transactions').status_code == 200


def test_unmigrated_legacy_schema_stays_usable_without_writes(monkeypatch):
    engine = sa.create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    LegacyBase.metadata.create_all(engine)
    monkeypatch.setattr(database, 'get_engine', lambda: engine)
    monkeypatch.setattr(transactions, 'transaction_model', lambda db: LegacyTransaction)
    monkeypatch.setattr(financial_service, 'transaction_model', lambda db: LegacyTransaction)
    with TestClient(app) as client:
        payload = {'description':'Legacy', 'amount':'12.34','category':'Test','transaction_type':'expense','transaction_date':'2026-10-10'}
        response = client.post('/api/transactions', json=payload)
        assert response.status_code == 201 and response.json()['currency'] == 'USD'
        assert client.get('/api/summary').json()['expenses'] == '12.34'
        assert client.post('/api/transactions', json={**payload,'currency':'INR'}).status_code == 409
        assert client.put('/api/transactions/1', json={**payload,'currency':'AED'}).status_code == 409
        assert client.get('/api/transactions/1').json()['amount'] == '12.34'
        assert 'currency' not in {c['name'] for c in sa.inspect(engine).get_columns('transactions')}
    engine.dispose()


def test_decimal_rounding_identity_and_indian_grouping():
    rates = fake_rates()
    value, _ = rates.convert(Decimal('800.00'), 'INR', 'AED', date(2026,10,10))
    assert value == Decimal('36.73')  # 36.725 -> 36.73, half up.
    assert rates.get('USD','USD',date(2026,10,10)).rate == 1
    assert currency_money(Decimal('1234567.89'),'INR') == '₹12,34,567.89'
    assert currency_money(Decimal('-1234.56'),'AED') == '-AED 1,234.56'


def test_cache_metadata_expiry_and_no_private_payloads():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={'base':'USD','quote':'INR','rate':'80.123456789','date':'2026-10-09'})
    rates = ExchangeRates(httpx.Client(transport=httpx.MockTransport(respond),base_url='https://api.frankfurter.dev'),clock=lambda:date(2026,11,12))
    first = rates.get('USD','INR',date(2026,10,10))
    second = rates.get('USD','INR',date(2026,10,10))
    assert first.rate == Decimal('80.123456789') and first.rate_date == date(2026,10,9)
    assert not first.cache_hit and second.cache_hit and len(calls) == 1
    assert set(calls[0].url.params) == {'date'} and calls[0].content == b''
    assert calls[0].url.host == 'api.frankfurter.dev'
    rates.cache[('USD','INR',date(2026,10,10))] = (0,first)
    rates.get('USD','INR',date(2026,10,10))
    assert len(calls) == 2


@pytest.mark.parametrize('data', [
    {'base':'USD','quote':'INR','rate':'0','date':'2026-10-10'},
    {'base':'USD','quote':'INR','rate':'NaN','date':'2026-10-10'},
    {'base':'AED','quote':'INR','rate':'80','date':'2026-10-10'},
    {'base':'USD','quote':'INR','rate':'80','date':'2026-10-11'},
    {'base':'USD','quote':'INR','rate':'80','date':'2026-10-01'},
])
def test_invalid_provider_data_never_becomes_a_rate(data):
    rates = ExchangeRates(httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=data)),base_url='https://api.frankfurter.dev'),clock=lambda:date(2026,11,12))
    with pytest.raises(RatesUnavailable):
        rates.get('USD','INR',date(2026,10,10))


def test_timeout_negative_cache_future_dates_and_bounded_fallback():
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout('PRIVATE_NETWORK_ERROR')
    rates = ExchangeRates(httpx.Client(transport=httpx.MockTransport(timeout),base_url='https://api.frankfurter.dev'),clock=lambda:date(2026,11,12))
    for _ in range(2):
        with pytest.raises(RatesUnavailable):
            rates.get('USD','INR',date(2026,10,10))
    assert len(calls) == 1
    with pytest.raises(RatesUnavailable, match='future'):
        rates.get('USD','INR',date(2026,12,1))
    assert len(calls) == 1
    missing = []
    def not_found(request):
        missing.append(request)
        return httpx.Response(404)
    rates = ExchangeRates(httpx.Client(transport=httpx.MockTransport(not_found),base_url='https://api.frankfurter.dev'),clock=lambda:date(2026,11,12))
    with pytest.raises(RatesUnavailable):
        rates.get('USD','INR',date(2026,10,10))
    assert len(missing) == 8


def test_converted_tiny_expenses_do_not_divide_by_zero(currency_client):
    client, engine, _ = currency_client
    with Session(engine) as db:
        db.add(Transaction(description='Tiny', amount=Decimal('0.01'),currency='INR', category='Test',transaction_type='expense',transaction_date=date(2026,10,10)))
        db.commit()
    response = client.get('/api/summary?reporting_currency=USD')
    assert response.status_code == 200
    assert response.json()['expenses'] == '0.00'
    assert response.json()['spending_by_category'][0]['share_percent'] == '0.00'
