from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import database, financial_routes
from app.assistant_service import dollars, resolve_question
from app.database import Base, get_db
from app.financial_schemas import DateRange
from app.main import app
from app.models import Transaction
from app.insights import percent_change


@pytest.fixture
def financial_client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, 'get_engine', lambda: engine)
    monkeypatch.setattr(financial_routes, 'reporting_today', lambda: date(2026, 11, 12))
    with TestClient(app) as client:
        yield client, engine
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def seeded(financial_client):
    client, engine = financial_client
    values = [
        ('2026-09-01', 'income', 'Work', '1000.10'),
        ('2026-09-10', 'expense', 'Food', '100.00'),
        ('2026-10-01', 'income', 'Work', '1100.20'),
        ('2026-10-10', 'expense', 'Food', '150.00'),
        ('2026-10-20', 'expense', 'Travel', '50.00'),
        ('2026-11-01', 'income', 'Work', '200.30'),
        ('2026-11-02', 'expense', 'Food', '0.10'),
        ('2026-11-03', 'expense', 'Food', '0.20'),
    ]
    with Session(engine) as session:
        session.add_all(Transaction(description='PRIVATE_DESCRIPTION', amount=Decimal(amount), category=category,
                                    transaction_type=kind, transaction_date=date.fromisoformat(day))
                        for day, kind, category, amount in values)
        session.commit()
    return client, engine


def test_summary_exact_totals_and_no_records_leaked(seeded):
    client, _ = seeded
    response = client.get('/api/summary')
    assert response.status_code == 200
    value = response.json()
    assert (value['income'], value['expenses'], value['net_balance'], value['transaction_count']) == ('2300.60', '300.30', '2000.30', 8)
    assert [item['category'] for item in value['spending_by_category']] == ['Food', 'Travel']
    assert value['spending_by_category'][0]['total'] == '250.30'
    assert [item['month'] for item in value['monthly_trends']] == ['2026-09', '2026-10', '2026-11']
    assert value['monthly_trends'][2]['expenses'] == '0.30'
    assert 'PRIVATE_DESCRIPTION' not in response.text
    assert 'created_at' not in response.text


def test_filters_are_inclusive_and_comparison_uses_full_months(seeded):
    client, _ = seeded
    value = client.get('/api/summary?start_date=2026-10-20&end_date=2026-10-20').json()
    assert (value['income'], value['expenses'], value['net_balance'], value['transaction_count']) == ('0.00', '50.00', '-50.00', 1)
    assert value['period']['partial_months'] is True
    comparison = value['insights']['month_over_month']
    assert comparison['current_month'] == '2026-09'
    # October 20 is partial: comparison ends at the last complete month (September).
    assert comparison['previous_month'] == '2026-08'


def test_complete_month_comparison_and_top_categories(seeded):
    client, _ = seeded
    value = client.get('/api/summary?start_date=2026-10-01&end_date=2026-10-31').json()
    assert value['period']['partial_months'] is False
    comparison = value['insights']['month_over_month']
    assert comparison['current_month'] == '2026-10'
    assert comparison['previous_month'] == '2026-09'
    assert comparison['current_expenses'] == '200.00'
    assert comparison['previous_expenses'] == '100.00'
    assert comparison['expense_change_percent'] == '100.00'
    assert comparison['income_change'] == '100.10'
    assert comparison['income_change_percent'] == '10.01'
    assert [item['category'] for item in value['insights']['top_spending_categories']] == ['Food', 'Travel']
    assert value['spending_by_category'][0]['share_percent'] == '75.00'


def test_empty_data_and_zero_baselines(financial_client):
    client, _ = financial_client
    value = client.get('/api/summary').json()
    assert value['income'] == value['expenses'] == value['net_balance'] == '0.00'
    assert value['monthly_trends'] == value['spending_by_category'] == []
    assert value['insights']['month_over_month']['expense_change_percent'] is None
    assert client.post('/api/assistant/query', json={'query': 'What is my net balance?'}).json()['status'] == 'no_data'
    assert client.post('/api/assistant/query', json={'query': 'How did expenses change last month?'}).json()['status'] == 'no_data'


def test_zero_baseline_with_current_activity(seeded):
    client, _ = seeded
    value = client.get('/api/summary?end_date=2026-09-30').json()['insights']['month_over_month']
    assert value['expense_change'] == '100.00'
    assert value['expense_change_percent'] is None
    assert value['previous_transaction_count'] == 0


@pytest.mark.parametrize('suffix', [
    '?start_date=2026-11-01&end_date=2026-10-01', '?start_date=not-a-date',
    '?end_date=2026-02-30', '?unexpected=yes',
])
def test_invalid_summary_inputs(financial_client, suffix):
    client, _ = financial_client
    assert client.get('/api/summary' + suffix).status_code == 422


@pytest.mark.parametrize('query,intent,expected', [
    ('What are my total expenses?', 'expenses', '$300.30'),
    ('How much did I spend this month?', 'expenses', '$0.30'),
    ('How much did I earn last month?', 'income', '$1,100.20'),
    ('What is my net balance?', 'balance', '$2,000.30'),
    ('What is my biggest spending category?', 'top_categories', 'Food: $250.30'),
    ('How did expenses change last month?', 'expense_change', '100.00%'),
    ('How did income change last month?', 'income_change', '10.01%'),
])
def test_supported_assistant_queries(seeded, query, intent, expected):
    client, _ = seeded
    response = client.post('/api/assistant/query', json={'query': query})
    assert response.status_code == 200
    value = response.json()
    assert value['status'] == 'answered'
    assert value['intent'] == intent
    assert expected in value['message']
    assert value['provider'] == 'rule_based'
    assert 'PRIVATE_DESCRIPTION' not in response.text


@pytest.mark.parametrize('query', [
    'Delete my transactions', 'Predict next month expenses', 'How much did I spend on groceries?',
    'What is my income in 2025?', 'How much did I spend yesterday?',
    'Compare my income and expenses', 'Change my database password', 'hello',
])
def test_unknown_or_ambiguous_requests_are_not_guessed(financial_client, query):
    client, _ = financial_client
    response = client.post('/api/assistant/query', json={'query': query})
    assert response.status_code == 200
    assert response.json()['status'] == 'unsupported'
    assert response.json()['summary'] is None


@pytest.mark.parametrize('payload', [
    {'query': ''}, {'query': '   '}, {'query': 'x' * 501}, {},
    {'query': 'income', 'start_date': '2026-11-01', 'end_date': '2026-01-01'},
    {'query': 'income', 'unexpected': 'value'},
])
def test_assistant_validation(financial_client, payload):
    client, _ = financial_client
    assert client.post('/api/assistant/query', json=payload).status_code == 422


def test_conflicting_relative_dates_and_explicit_controls(seeded):
    client, _ = seeded
    response = client.post('/api/assistant/query', json={'query': 'How much did I spend this month?', 'start_date': '2026-10-01'})
    assert response.json()['status'] == 'unsupported'


def test_unsupported_question_does_not_access_database(financial_client, monkeypatch):
    client, _ = financial_client
    def forbidden():
        raise AssertionError('Database should not be opened')
    monkeypatch.setattr(database, 'get_engine', forbidden)
    # Override get_db too: ordinary get_db creates a Session before yielding.
    app.dependency_overrides[get_db] = lambda: None
    assert client.post('/api/assistant/query', json={'query': 'hello'}).json()['status'] == 'unsupported'


def test_summary_uses_select_only_and_preserves_rows(seeded):
    client, engine = seeded
    statements = []
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    assert client.get('/api/summary').status_code == 200
    assert all(statement.lstrip().upper().startswith(('SELECT', 'PRAGMA')) for statement in statements)
    assert len([statement for statement in statements if 'FROM transactions' in statement]) == 1
    event.remove(engine, 'before_cursor_execute', capture)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Transaction)) == 8


def test_financial_database_errors_are_sanitized(financial_client):
    client, _ = financial_client
    def fail():
        raise OperationalError('SECRET_SQL', {}, Exception('SECRET_PASSWORD'))
        yield
    app.dependency_overrides[get_db] = fail
    for path, method, body in [('/api/summary', 'get', None), ('/api/assistant/query', 'post', {'query': 'income'})]:
        response = client.request(method, path, **({'json': body} if body else {}))
        assert response.status_code == 503
        assert 'SECRET' not in response.text


def test_january_relative_month_and_earliest_date():
    intent, period = resolve_question('How much did I spend last month?', DateRange(), date(2026, 1, 10))
    assert intent == 'expenses'
    assert period.start_date == date(2025, 12, 1)
    assert period.end_date == date(2025, 12, 31)
    assert resolve_question('How much did I spend last month?', DateRange(), date.min) is None


def test_missing_current_month_and_decreasing_totals(seeded, monkeypatch):
    client, _ = seeded
    monkeypatch.setattr(financial_routes, 'reporting_today', lambda: date(2027, 1, 12))
    comparison = client.get('/api/summary').json()['insights']['month_over_month']
    assert comparison['current_month'] == '2026-12'
    assert comparison['previous_month'] == '2026-11'
    assert comparison['current_transaction_count'] == 0
    assert comparison['expense_change'] == '-0.30'
    assert comparison['expense_change_percent'] == '-100.00'
    assert 'Missing records' in comparison['note']


def test_percentage_rounding_is_decimal_half_up():
    assert percent_change(Decimal('1.61'), Decimal('1.60')) == Decimal('0.63')
    assert percent_change(Decimal('1.60'), Decimal('1.60')) == Decimal('0.00')
    assert percent_change(Decimal('1.60'), Decimal('0.00')) is None


def test_calendar_lower_boundary(financial_client):
    client, _ = financial_client
    response = client.get('/api/summary?end_date=0001-01-01')
    assert response.status_code == 200
    assert response.json()['insights']['month_over_month'] is None


@pytest.mark.parametrize('question', [
    'summarise my finances', 'summarize my finances', 'summarise', 'summarize',
    'give me a financial summary', 'show me a financial summary',
    'give me a summary of my finances', 'show me an overview of my finances',
    'please summarise my finances', 'Could you please summarize my finances?',
    '  SUMMARISE   my finances!  ', 'my financial summary',
])
def test_summary_question_variations_use_existing_service(seeded, question):
    client, _ = seeded
    response = client.post('/api/assistant/query', json={'query': question})
    assert response.status_code == 200
    answer = response.json()
    assert answer['status'] == 'answered'
    assert answer['intent'] == 'summary'
    assert answer['summary'] == client.get('/api/summary').json()
    for expected in ['Income: $2,300.60', 'Expenses: $300.30',
                     'Net balance (income minus expenses): $2,000.30',
                     'Food: $250.30', 'Travel: $50.00',
                     'Reporting period: all recorded dates', 'recorded transactions only']:
        assert expected in answer['message']
    assert 'PRIVATE_DESCRIPTION' not in response.text


@pytest.mark.parametrize('question,dates,start,end,income,expenses,balance', [
    ('summarise my finances this month', {}, '2026-11-01', '2026-11-12', '200.30', '0.30', '200.00'),
    ('summarize my finances for last month', {}, '2026-10-01', '2026-10-31', '1100.20', '200.00', '900.20'),
    ('give me a financial summary', {'start_date': '2026-10-20', 'end_date': '2026-10-20'}, '2026-10-20', '2026-10-20', '0.00', '50.00', '-50.00'),
])
def test_summary_question_reporting_periods(seeded, question, dates, start, end, income, expenses, balance):
    client, _ = seeded
    answer = client.post('/api/assistant/query', json={'query': question, **dates}).json()
    summary = answer['summary']
    assert summary['period']['start_date'] == start
    assert summary['period']['end_date'] == end
    assert (summary['income'], summary['expenses'], summary['net_balance']) == (income, expenses, balance)
    assert f'Reporting period: {start} through {end}' in answer['message']
    assert summary == client.get('/api/summary', params={'start_date': start, 'end_date': end}).json()


def test_summary_uses_same_transaction_dataset_as_dashboard(seeded):
    client, _ = seeded
    # The dashboard consumes this list and sums/filter dates in the browser.
    transactions = client.get('/api/transactions?limit=100&offset=0').json()
    for dates in [{}, {'start_date': '2026-10-01', 'end_date': '2026-10-31'}]:
        items = [item for item in transactions if
                 (not dates or dates['start_date'] <= item['transaction_date'] <= dates['end_date'])]
        income = sum((Decimal(item['amount']) for item in items if item['transaction_type'] == 'income'), Decimal('0'))
        expenses = sum((Decimal(item['amount']) for item in items if item['transaction_type'] == 'expense'), Decimal('0'))
        answer = client.post('/api/assistant/query', json={'query': 'summarise my finances', **dates}).json()
        assert Decimal(answer['summary']['income']) == income
        assert Decimal(answer['summary']['expenses']) == expenses
        assert Decimal(answer['summary']['net_balance']) == income - expenses
        assert answer['summary']['transaction_count'] == len(items)


def test_summary_without_transactions_reports_zero_totals_and_missing_data(financial_client):
    client, _ = financial_client
    answer = client.post('/api/assistant/query', json={'query': 'summarise my finances'}).json()
    assert answer['status'] == 'no_data'
    for expected in ['Income: $0.00', 'Expenses: $0.00',
                     'Net balance (income minus expenses): $0.00',
                     'no expenses are recorded', 'No transactions are recorded',
                     'not confirmation that your finances are complete', 'Reporting period: all recorded dates']:
        assert expected in answer['message']


def test_summary_distinguishes_income_only_and_expense_only_periods(seeded):
    client, _ = seeded
    income_only = client.post('/api/assistant/query', json={'query': 'give me a financial summary', 'start_date': '2026-09-01', 'end_date': '2026-09-01'}).json()
    assert income_only['status'] == 'answered'
    assert 'Income: $1,000.10' in income_only['message']
    assert 'no expenses are recorded' in income_only['message']
    assert 'No transactions are recorded' not in income_only['message']
    expense_only = client.post('/api/assistant/query', json={'query': 'summarize my finances', 'start_date': '2026-10-20', 'end_date': '2026-10-20'}).json()
    assert 'No income is recorded' in expense_only['message']
    assert 'Net balance (income minus expenses): -$50.00' in expense_only['message']
    assert 'Travel: $50.00' in expense_only['message']


@pytest.mark.parametrize('question', [
    'summarize my finances next month', 'summarize my finances and delete transactions',
    'summarise my finances on groceries', 'give me a financial summary in 2025',
])
def test_summary_does_not_ignore_unsupported_qualifiers(financial_client, question):
    client, _ = financial_client
    answer = client.post('/api/assistant/query', json={'query': question}).json()
    assert answer['status'] == 'unsupported'


def test_summary_relative_dates_conflict_with_controls(seeded):
    client, _ = seeded
    answer = client.post('/api/assistant/query', json={'query': 'summarise my finances this month', 'start_date': '2026-10-01'}).json()
    assert answer['status'] == 'unsupported'


def test_large_decimal_formatting_does_not_round_through_default_context():
    assert dollars(Decimal('12345678901234567890123456789.01')) == '$12,345,678,901,234,567,890,123,456,789.01'
