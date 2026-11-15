"""Only the explicitly allowlisted restored test database; all DDL rolls back."""
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.migration import MigrationContext

from test_currency_migration import isolated_migration


def test_postgres_profile_api_isolation(isolated_migration, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from app.database import get_db
    from app.main import app
    from app import financial_service, transactions
    from test_multicurrency import fake_rates

    connection, config, _ = isolated_migration
    command.upgrade(config, '0003')
    before = connection.execute(sa.text('SELECT * FROM transactions ORDER BY id')).mappings().all()
    # Preserve the restored transaction sequence even though these writes roll back.
    fixture_id = max(row['id'] for row in before) + 10000
    connection.execute(sa.text(f'ALTER TABLE transactions ALTER COLUMN id SET DEFAULT {int(fixture_id)}'))
    rates = fake_rates()
    for module in [financial_service, transactions]:
        monkeypatch.setattr(module, 'get_exchange_rates', lambda: rates)
    def isolated_db():
        with Session(bind=connection, join_transaction_mode='create_savepoint') as db:
            yield db
    app.dependency_overrides[get_db] = isolated_db
    try:
        with TestClient(app) as client:
            mom = client.post('/api/profiles', json={'name': 'Mom'}).json()['id']
            payload = {'profile_id': mom, 'description': 'Test only', 'amount': '800.00', 'currency': 'INR',
                       'transaction_type': 'expense', 'category': 'Food', 'transaction_date': '2026-10-10'}
            response = client.post('/api/transactions', json=payload)
            assert response.status_code == 201
            row_id = response.json()['id']
            assert client.get(f'/api/transactions/{row_id}').status_code == 404
            assert len(client.get('/api/transactions').json()) == len(before)
            assert client.get(f'/api/summary?profile_id={mom}').json()['expenses'] == '10.00'
            assert client.get(f'/api/summary?profile_id={mom}&reporting_currency=INR').json()['expenses'] == '800.00'
            answer = client.post('/api/assistant/query', json={'query': 'total expenses', 'profile_id': mom}).json()
            assert answer['summary']['transaction_count'] == 1
            assert answer['summary']['expenses'] == '10.00'
            assert client.patch(f'/api/profiles/{mom}', json={'archived': True}).status_code == 200
            assert client.delete(f'/api/transactions/{row_id}?profile_id={mom}').status_code == 409
            assert len(client.get('/api/transactions?profile_id=all').json()) == len(before) + 1
            original_ids = [row['id'] for row in before]
            assert [dict(row) for row in connection.execute(sa.text('SELECT * FROM transactions ORDER BY id')).mappings() if row['id'] in original_ids] == [dict(row) for row in before]
    finally:
        app.dependency_overrides.clear()


def test_interrupted_profile_migration_rolls_back(isolated_migration):
    connection, config, _ = isolated_migration
    command.upgrade(config, '0002')
    before = connection.execute(sa.text('SELECT * FROM transactions ORDER BY id')).mappings().all()
    def interrupt(conn, cursor, statement, parameters, context, many):
        if statement.startswith('CREATE INDEX ix_transactions_profile_id_date'):
            raise RuntimeError('Simulated migration interruption')
    sa.event.listen(connection, 'before_cursor_execute', interrupt)
    try:
        with pytest.raises(RuntimeError, match='Simulated'):
            with connection.begin_nested():
                command.upgrade(config, '0003')
    finally:
        sa.event.remove(connection, 'before_cursor_execute', interrupt)
    assert MigrationContext.configure(connection).get_current_heads() == ('0002',)
    assert not sa.inspect(connection).has_table('profiles')
    assert connection.execute(sa.text('SELECT * FROM transactions ORDER BY id')).mappings().all() == before


def test_profile_migration_preserves_every_existing_field(isolated_migration):
    connection, config, _ = isolated_migration
    command.upgrade(config, '0002')
    # More currencies/dates, explicit negative IDs avoid changing existing sequences.
    for row_id, currency, day in [(-100, 'INR', '2026-10-01'), (-101, 'AED', '2026-09-01')]:
        connection.execute(sa.text("INSERT INTO transactions (id, description, amount, category, transaction_type, transaction_date, currency) "
                                   "VALUES (:id, 'Original', 123.45, 'Test', 'expense', :day, :currency)"),
                           {'id': row_id, 'day': day, 'currency': currency})
    before = connection.execute(sa.text('SELECT * FROM transactions ORDER BY id')).mappings().all()
    command.upgrade(config, '0003')
    assert MigrationContext.configure(connection).get_current_heads() == ('0003',)
    profiles = connection.execute(sa.text('SELECT * FROM profiles')).mappings().all()
    assert len(profiles) == 1 and profiles[0]['name'] == 'My Profile' and profiles[0]['is_default']
    after = connection.execute(sa.text('SELECT * FROM transactions ORDER BY id')).mappings().all()
    assert [{key: value for key, value in row.items() if key != 'profile_id'} for row in after] == [dict(row) for row in before]
    assert {row['profile_id'] for row in after} == {profiles[0]['id']}
    inspector = sa.inspect(connection)
    assert next(column for column in inspector.get_columns('transactions') if column['name'] == 'profile_id')['nullable'] is False
    assert {'ix_transactions_profile_id_id', 'ix_transactions_profile_id_date'} <= {index['name'] for index in inspector.get_indexes('transactions')}
    foreign_key = inspector.get_foreign_keys('transactions')[0]
    assert foreign_key['referred_table'] == 'profiles' and foreign_key['options']['ondelete'] == 'RESTRICT'
    for statement in [
        'UPDATE transactions SET profile_id = NULL',
        'UPDATE transactions SET profile_id = -999',
        f"DELETE FROM profiles WHERE id = {int(profiles[0]['id'])}",
        "INSERT INTO profiles (name, is_default) VALUES ('Another default', true)",
        "UPDATE profiles SET archived_at = now() WHERE is_default",
        "INSERT INTO profiles (name) VALUES ('   ')",
    ]:
        with pytest.raises(sa.exc.IntegrityError):
            with connection.begin_nested():
                connection.execute(sa.text(statement))
    with pytest.raises(RuntimeError, match='discard'):
        command.downgrade(config, '0002')
    assert connection.execute(sa.text('SELECT count(*) FROM transactions')).scalar() == len(before)
    assert MigrationContext.configure(connection).get_current_heads() == ('0003',)
