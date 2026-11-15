"""Explicit one-time setup of a NEW, empty finflow_demo PostgreSQL database only.

Never reads backend/.env or DB_* variables. No drop, reset, or overwrite path.
"""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def validate_target(raw_url, confirmation):
    if not raw_url or confirmation != 'finflow_demo':
        raise ValueError('Set DEMO_DATABASE_URL and pass --confirm-database finflow_demo.')
    url = make_url(raw_url)
    if url.get_backend_name() not in {'postgres', 'postgresql'} or url.database != 'finflow_demo':
        raise ValueError('Only a separate PostgreSQL database named finflow_demo is allowed.')
    if url.query.get('sslmode') != 'verify-full':
        raise ValueError('DEMO_DATABASE_URL must include sslmode=verify-full and a trusted root certificate.')
    return url.set(drivername='postgresql+psycopg')


def initialize(connection):
    # Check BEFORE migrations; reruns refuse even partially populated databases.
    # No application engine is imported and no implicit local credentials exist.
    if inspect(connection).get_table_names(schema='public'):
        raise ValueError('Refusing a nonempty database. No reset or overwrite is supported.')
    config = Config(str(Path(__file__).with_name('alembic.ini')))
    config.attributes['connection'] = connection
    command.upgrade(config, '0003')
    if connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() != '0003':
        raise ValueError('Unexpected database revision.')

    from app.models import Profile, Transaction
    fixture = json.loads(Path(__file__).with_name('demo_data.json').read_text(encoding='utf-8'))
    default_id = connection.execute(text('SELECT id FROM profiles WHERE is_default')).scalar_one()
    connection.execute(Profile.__table__.update().where(Profile.id == default_id).values(name='Demo household'))
    profile_ids = [default_id]
    for name in fixture['profiles']:
        profile_ids.append(connection.execute(Profile.__table__.insert().values(name=name).returning(Profile.id)).scalar_one())
    for record in fixture['transactions']:
        values = dict(record)
        values['profile_id'] = profile_ids[values.pop('profile')]
        values['transaction_date'] = date.fromisoformat(values['transaction_date'])
        values['amount'] = Decimal(values['amount'])
        connection.execute(Transaction.__table__.insert().values(**values))
    connection.execute(Profile.__table__.update().where(Profile.id == profile_ids[2]).values(archived_at=datetime.now(timezone.utc)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-database', required=True)
    args = parser.parse_args()
    try:
        target = validate_target(os.environ.get('DEMO_DATABASE_URL'), args.confirm_database)
        engine = create_engine(target, hide_parameters=True, connect_args={'connect_timeout': 5})
        with engine.begin() as connection:
            if connection.execute(text('SELECT current_database()')).scalar_one() != 'finflow_demo':
                raise ValueError('Unexpected database target.')
            initialize(connection)
        engine.dispose()
    except Exception:
        # Database URLs and driver errors can contain credentials. Do not print them.
        raise SystemExit('Demo initialization refused or failed; transaction rolled back. '
                         'Check the explicit demo target, TLS, permissions, and empty-database requirement.') from None
    print('Created fictional demo at revision 0003. No existing database was reset.')


if __name__ == '__main__':
    main()
