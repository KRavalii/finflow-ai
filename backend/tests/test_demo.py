"""Public-demo protections, using isolated SQLite only; never the live DB."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import config, financial_routes
from app.config import RuntimeSettings
from app.database import Base, get_db
from app.main import create_app
from app.models import Profile, Transaction
import prepare_demo


@pytest.fixture
def demo():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)'))
        conn.execute(text("INSERT INTO alembic_version VALUES ('0003')"))
    with Session(engine) as db:
        db.add(Transaction(description='Fictional test', amount=Decimal('20.00'), category='Food',
                           transaction_type='expense', transaction_date=date(2026, 10, 10), currency='USD'))
        db.commit()
    app = create_app(RuntimeSettings(demo_mode=True, cors_origins=['https://demo.example']))
    def isolated_db():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = isolated_db
    with TestClient(app) as client:
        yield client, engine, app
    engine.dispose()


@pytest.mark.parametrize('method,path', [
    ('POST', '/api/transactions'), ('PUT', '/api/transactions/1'),
    ('DELETE', '/api/transactions/1'), ('POST', '/api/profiles'),
    ('PATCH', '/api/profiles/1'), ('DELETE', '/api/profiles/1'),
    ('POST', '/future-write-route'), ('TRACE', '/api/health'),
    ('POST', '/api/assistant/query/'), ('PATCH', '/api/assistant/query'),
])
def test_demo_blocks_unsafe_requests_before_database_access(demo, method, path):
    client, engine, app = demo
    def forbidden_db():
        raise AssertionError('Blocked requests must never open a DB session')
    app.dependency_overrides[get_db] = forbidden_db
    response = client.request(method, path, json={'name': 'Tampered'})
    assert response.status_code == 403
    assert response.json()['detail']['code'] == 'demo_read_only'
    with Session(engine) as db:
        assert len(db.scalars(select(Transaction)).all()) == 1
        assert db.scalar(select(Profile)).name == 'My Profile'


def test_demo_keeps_reads_assistant_and_historical_policy(demo, monkeypatch):
    client, _, _ = demo
    monkeypatch.setattr(financial_routes, 'reporting_today', lambda: date(2026, 11, 14))
    for path in ['/healthz', '/api/health', '/api/readiness', '/api/profiles', '/api/transactions', '/docs']:
        assert client.get(path).status_code == 200
    assert client.get('/api/config').json() == {'demo_mode': True}
    response = client.get('/api/summary')
    assert response.status_code == 200
    assert response.json()['expenses'] == '20.00'
    assert response.json()['rate_policy'] == 'historical'
    assert client.post('/api/assistant/query', json={'query': 'total expenses'}).status_code == 200


def test_demo_cors_allows_only_configured_origin_and_keeps_guard(demo):
    client, _, _ = demo
    allowed = client.options('/api/transactions', headers={
        'Origin': 'https://demo.example', 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'})
    assert allowed.status_code == 200
    assert allowed.headers['access-control-allow-origin'] == 'https://demo.example'
    blocked = client.post('/api/transactions', json={}, headers={'Origin': 'https://demo.example'})
    assert blocked.status_code == 403
    assert blocked.headers['access-control-allow-origin'] == 'https://demo.example'
    assert 'access-control-allow-origin' not in client.get('/api/health', headers={'Origin': 'https://evil.example'}).headers


@pytest.mark.parametrize('changes', [
    {'FINFLOW_DEMO_MODE': 'false'}, {'DB_NAME': 'finflow_db'},
    {'CORS_ORIGINS': '*'}, {'CORS_ORIGINS': 'http://demo.example'},
    {'CORS_ORIGINS': 'https://demo.example/'}, {'FINFLOW_DEMO_MODE': 'typo'},
    {'CORS_ORIGINS': 'https://user:secret@demo.example'},
])
def test_invalid_production_configuration_fails_closed(monkeypatch, changes):
    values = {'APP_ENV': 'production', 'FINFLOW_DEMO_MODE': 'true', 'DB_NAME': 'finflow_demo', **changes}
    monkeypatch.setattr(config, 'environment_values', lambda: values)
    with pytest.raises(RuntimeError):
        config.get_runtime_settings()


def test_production_requires_verified_tls(monkeypatch):
    values = dict(APP_ENV='production', FINFLOW_DEMO_MODE='true', DB_NAME='finflow_demo',
                  DB_HOST='db.example', DB_PORT='5432', DB_USER='finflow_reader', DB_PASSWORD='placeholder')
    monkeypatch.setattr(config, 'environment_values', lambda: values)
    assert config.get_settings().database_url.query['sslmode'] == 'verify-full'
    values['DB_SSLMODE'] = 'require'
    with pytest.raises(RuntimeError):
        config.get_settings()


@pytest.mark.parametrize('url,confirmation', [
    (None, 'finflow_demo'), ('postgresql://example/finflow_db?sslmode=verify-full', 'finflow_demo'),
    ('sqlite:///finflow_demo', 'finflow_demo'),
    ('postgresql://example/finflow_demo?sslmode=require', 'finflow_demo'),
    ('postgresql://example/finflow_demo?sslmode=verify-full', 'finflow_db'),
])
def test_initializer_rejects_unsafe_targets(url, confirmation):
    with pytest.raises(ValueError):
        prepare_demo.validate_target(url, confirmation)


PROJECT_REF = 'abcdefghijklmnopqrst'
OTHER_REF = 'zyxwvutsrqponmlkjihg'
POOLER_HOST = 'aws-0-us-east-1.pooler.supabase.com'


def supabase_values(**changes):
    return dict(APP_ENV='production', FINFLOW_DEMO_MODE='true', DB_NAME='postgres',
                DB_HOST=POOLER_HOST, DB_PORT='5432', DB_USER=f'finflow_reader.{PROJECT_REF}',
                DB_PASSWORD='test-only', FINFLOW_SUPABASE_PROJECT_REF=PROJECT_REF,
                DB_SSLMODE='verify-full', **changes)


@pytest.mark.parametrize('host,user', [
    (POOLER_HOST, f'finflow_reader.{PROJECT_REF}'),
    (f'db.{PROJECT_REF}.supabase.co', 'finflow_reader'),
])
def test_confirmed_supabase_runtime_and_initializer_agree(monkeypatch, host, user):
    values = supabase_values()
    values.update(DB_HOST=host, DB_USER=user)
    monkeypatch.setattr(config, 'environment_values', lambda: values)
    assert config.get_runtime_settings().demo_mode
    assert config.get_settings().name == 'postgres'
    raw = f'postgresql://{user}:test-only@{host}:5432/postgres?sslmode=verify-full'
    assert prepare_demo.validate_target(raw, 'postgres', PROJECT_REF).database == 'postgres'


@pytest.mark.parametrize('host,user', [
    (POOLER_HOST, f'postgres.{PROJECT_REF}'),
    (POOLER_HOST, f'another_reader.{PROJECT_REF}'),
    (POOLER_HOST, 'finflow_reader'),
    (f'db.{PROJECT_REF}.supabase.co', 'postgres'),
    (f'db.{PROJECT_REF}.supabase.co', f'finflow_reader.{PROJECT_REF}'),
])
def test_production_refuses_non_runtime_database_users_before_startup(monkeypatch, host, user):
    values = supabase_values()
    values.update(DB_HOST=host, DB_USER=user)
    monkeypatch.setattr(config, 'environment_values', lambda: values)
    with pytest.raises(RuntimeError):
        create_app()


@pytest.mark.parametrize('user', ['postgres', 'another_reader'])
def test_other_production_hosting_also_requires_runtime_user(monkeypatch, user):
    values = dict(APP_ENV='production', FINFLOW_DEMO_MODE='true', DB_NAME='finflow_demo',
                  DB_HOST='db.example', DB_PORT='5432', DB_USER=user, DB_PASSWORD='test-only',
                  DB_SSLMODE='verify-full')
    monkeypatch.setattr(config, 'environment_values', lambda: values)
    with pytest.raises(RuntimeError, match='finflow_reader'):
        config.get_settings()


@pytest.mark.parametrize('demo_mode,name,host,user', [
    ('false', 'finflow_db', 'localhost', 'postgres'),
    ('true', 'postgres', POOLER_HOST, f'postgres.{PROJECT_REF}'),
])
def test_development_and_explicit_setup_targets_keep_existing_user_behavior(monkeypatch, demo_mode, name, host, user):
    values = supabase_values()
    values.update(APP_ENV='development', FINFLOW_DEMO_MODE=demo_mode,
                  DB_NAME=name, DB_HOST=host, DB_USER=user)
    monkeypatch.setattr(config, 'environment_values', lambda: values)
    assert config.get_settings().user == user
    cloud_setup = f'postgresql://postgres.{PROJECT_REF}:test-only@{POOLER_HOST}:5432/postgres?sslmode=verify-full'
    assert prepare_demo.validate_target(cloud_setup, 'postgres', PROJECT_REF).username == f'postgres.{PROJECT_REF}'


@pytest.mark.parametrize('changes', [
    {'FINFLOW_SUPABASE_PROJECT_REF': None},
    {'FINFLOW_SUPABASE_PROJECT_REF': 'not-a-project'},
    {'DB_NAME': 'finflow_db'},
    {'DB_HOST': 'localhost'},
    {'DB_HOST': '127.0.0.1'},
    {'DB_HOST': f'db.{OTHER_REF}.supabase.co'},
    {'DB_HOST': f'db.{PROJECT_REF}.supabase.co.evil.example'},
    {'DB_USER': f'finflow_reader.{OTHER_REF}'},
    {'DB_PORT': '6543'},
    {'DB_SSLMODE': 'require'},
])
def test_supabase_runtime_rejects_unsafe_configuration(monkeypatch, changes):
    values = supabase_values()
    values.update(changes)
    monkeypatch.setattr(config, 'environment_values', lambda: values)
    with pytest.raises(RuntimeError):
        config.get_settings()


@pytest.mark.parametrize('host,user,port,name,ref,extra', [
    (POOLER_HOST, f'postgres.{PROJECT_REF}', 5432, 'postgres', None, ''),
    ('localhost', 'postgres', 5432, 'postgres', PROJECT_REF, ''),
    (f'db.{OTHER_REF}.supabase.co', 'postgres', 5432, 'postgres', PROJECT_REF, ''),
    (POOLER_HOST, f'postgres.{OTHER_REF}', 5432, 'postgres', PROJECT_REF, ''),
    (POOLER_HOST, f'postgres.{PROJECT_REF}', 6543, 'postgres', PROJECT_REF, ''),
    (POOLER_HOST, f'postgres.{PROJECT_REF}', 5432, 'finflow_db', PROJECT_REF, ''),
    (POOLER_HOST, f'postgres.{PROJECT_REF}', 5432, 'postgres', PROJECT_REF, '&host=localhost'),
    (POOLER_HOST, f'postgres.{PROJECT_REF}', 5432, 'postgres', PROJECT_REF, '&hostaddr=127.0.0.1'),
    (POOLER_HOST, f'postgres.{PROJECT_REF}', 5432, 'postgres', PROJECT_REF, '&dbname=finflow_db'),
])
def test_supabase_initializer_rejects_unconfirmed_or_overridden_targets(host, user, port, name, ref, extra):
    raw = f'postgresql://{user}:test-only@{host}:{port}/{name}?sslmode=verify-full{extra}'
    with pytest.raises(ValueError):
        prepare_demo.validate_target(raw, 'postgres', ref)


def test_existing_finflow_demo_initializer_still_works():
    target = prepare_demo.validate_target(
        'postgresql://setup:test-only@db.example/finflow_demo?sslmode=verify-full', 'finflow_demo')
    assert target.database == 'finflow_demo'


def test_initializer_checks_actual_database_before_initializing():
    connection = SimpleNamespace(execute=lambda query: SimpleNamespace(scalar_one=lambda: 'finflow_db'))
    with pytest.raises(ValueError):
        prepare_demo.verify_connected_database(connection, 'postgres')


def test_initializer_refuses_existing_database_before_migrations(monkeypatch):
    engine = create_engine('sqlite://')
    monkeypatch.setattr(prepare_demo, 'inspect', lambda conn: SimpleNamespace(
        get_table_names=lambda **kwargs: inspect(conn).get_table_names()))
    def unexpected(*args):
        raise AssertionError('Must not run migrations on an existing database')
    monkeypatch.setattr(prepare_demo.command, 'upgrade', unexpected)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE existing_records (id INTEGER)'))
        conn.execute(text('INSERT INTO existing_records VALUES (42)'))
        with pytest.raises(ValueError):
            prepare_demo.initialize(conn)
        assert conn.execute(text('SELECT id FROM existing_records')).scalar_one() == 42
    engine.dispose()


def test_initializer_fictional_fixture_and_repeat_refusal(monkeypatch):
    engine = create_engine('sqlite://')
    monkeypatch.setattr(prepare_demo, 'inspect', lambda conn: SimpleNamespace(
        get_table_names=lambda **kwargs: inspect(conn).get_table_names()))
    # Exercise the fixture inserts without running PostgreSQL migrations.
    def simulated_migrations(config, revision):
        assert revision == '0003'
        conn = config.attributes['connection']
        Base.metadata.create_all(conn)
        conn.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32))'))
        conn.execute(text("INSERT INTO alembic_version VALUES ('0003')"))
    monkeypatch.setattr(prepare_demo.command, 'upgrade', simulated_migrations)
    with engine.begin() as conn:
        prepare_demo.initialize(conn)
        rows = conn.execute(select(Transaction.__table__)).mappings().all()
        assert len(rows) == 17
        assert all(row['description'].startswith('Fictional ') for row in rows)
        assert {row['currency'] for row in rows} == {'USD', 'INR', 'AED'}
        assert len(conn.execute(select(Profile.__table__)).all()) == 3
        with pytest.raises(ValueError):
            prepare_demo.initialize(conn)
        assert len(conn.execute(select(Transaction.__table__)).all()) == 17
    engine.dispose()


def test_same_origin_spa_and_unknown_api_are_separate(tmp_path, monkeypatch):
    # No real frontend files or server processes are required for this check.
    dist = tmp_path / 'frontend' / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<html>Fictional demo</html>')
    (dist / 'assets' / 'app.js').write_text('console.log("demo")')
    import app.main as main
    monkeypatch.setattr(main, '__file__', str(tmp_path / 'backend' / 'app' / 'main.py'))
    with TestClient(create_app(RuntimeSettings(demo_mode=True, serve_frontend=True))) as client:
        for path in ['/', '/transactions', '/analytics', '/assistant', '/assets/app.js']:
            assert client.get(path).status_code == 200
        for path in ['/api/does-not-exist', '/assets/missing.js', '/unknown']:
            assert client.get(path).status_code == 404
