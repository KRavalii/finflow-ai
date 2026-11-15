"""Opt-in PostgreSQL migration safety checks; never connect to finflow_db.

All DDL and fixture rows run inside a transaction that is always rolled back,
leaving the restored database at its original schema and revision.
"""
import os
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext

from app.config import get_settings


@pytest.fixture
def isolated_migration():
    target = os.environ.get('FINFLOW_MIGRATION_TEST_DATABASE')
    if not target:
        pytest.skip('Set FINFLOW_MIGRATION_TEST_DATABASE=finflow_restore_test to opt in.')
    # A strict allowlist prevents accidental selection of the application DB.
    if target != 'finflow_restore_test':
        pytest.fail('Migration safety tests only allow finflow_restore_test.')
    settings = get_settings()
    if target == settings.name:
        pytest.fail('Migration test database must differ from the application database.')
    engine = sa.create_engine(settings.database_url.set(database=target), hide_parameters=True,
                              connect_args={'connect_timeout': 5})
    connection = engine.connect()
    transaction = connection.begin()
    try:
        assert connection.scalar(sa.text('SELECT current_database()')) == target
        assert MigrationContext.configure(connection).get_current_heads() == ('0001',)
        original = connection.execute(sa.text('SELECT * FROM public.transactions ORDER BY id')).mappings().all()
        assert len(original) == 1, 'Expected independently verified restored backup with one transaction.'
        assert 'currency' not in original[0]
        config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
        config.attributes['connection'] = connection
        yield connection, config, original
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def existing_rows(connection):
    return connection.execute(sa.text(
        'SELECT id, description, amount, category, transaction_type, transaction_date, created_at '
        'FROM public.transactions ORDER BY id'
    )).mappings().all()


def test_upgrade_downgrade_preserves_backup_and_defaults(isolated_migration):
    connection, config, original = isolated_migration
    command.upgrade(config, '0002')
    assert MigrationContext.configure(connection).get_current_heads() == ('0002',)
    assert existing_rows(connection) == original
    assert connection.execute(sa.text('SELECT currency FROM transactions')).scalars().all() == ['USD']
    columns = {column['name']: column for column in sa.inspect(connection).get_columns('transactions')}
    assert columns['currency']['nullable'] is False
    assert 'USD' in columns['currency']['default']
    assert 'ck_transactions_currency' in {item['name'] for item in sa.inspect(connection).get_check_constraints('transactions')}

    # Use a negative explicit ID so testing defaults cannot advance a sequence.
    # Even this fixture insert is rolled back before downgrade.
    with connection.begin_nested() as savepoint:
        currency = connection.scalar(sa.text(
            "INSERT INTO transactions (id, description, amount, category, transaction_type, transaction_date) "
            "VALUES (-1, 'Migration default verification', 1.23, 'Test', 'expense', '2026-11-12') RETURNING currency"
        ))
        assert currency == 'USD'
        savepoint.rollback()
    with pytest.raises(sa.exc.IntegrityError):
        with connection.begin_nested():
            connection.execute(sa.text("UPDATE transactions SET currency = 'EUR'"))
    with pytest.raises(sa.exc.IntegrityError):
        with connection.begin_nested():
            connection.execute(sa.text('UPDATE transactions SET currency = NULL'))
    assert existing_rows(connection) == original

    command.downgrade(config, '0001')
    assert MigrationContext.configure(connection).get_current_heads() == ('0001',)
    assert 'currency' not in {column['name'] for column in sa.inspect(connection).get_columns('transactions')}
    assert existing_rows(connection) == original
    command.upgrade(config, '0002')
    assert existing_rows(connection) == original
    assert connection.scalar(sa.text('SELECT currency FROM transactions')) == 'USD'


@pytest.mark.parametrize('currency', ['INR', 'AED'])
def test_downgrade_refuses_to_discard_non_usd(isolated_migration, currency):
    connection, config, original = isolated_migration
    command.upgrade(config, '0002')
    connection.execute(sa.text(
        "INSERT INTO transactions (id, description, amount, category, transaction_type, transaction_date, currency) "
        "VALUES (-1, 'Migration guard verification', 12.34, 'Test', 'expense', '2026-11-12', :currency)"
    ), {'currency': currency})
    with pytest.raises(RuntimeError, match='Downgrade refused'):
        command.downgrade(config, '0001')
    assert MigrationContext.configure(connection).get_current_heads() == ('0002',)
    assert connection.scalar(sa.text('SELECT currency FROM transactions WHERE id=-1')) == currency
    assert connection.scalar(sa.text('SELECT amount FROM transactions WHERE id=-1')) == Decimal('12.34')
    assert [row for row in existing_rows(connection) if row['id'] != -1] == original
