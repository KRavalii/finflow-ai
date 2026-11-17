"""Production simulations use dummy values; never connect to a database."""
import logging

import pytest

from app import config


REF = 'abcdefghijklmnopqrst'


def production_values(**changes):
    return dict(APP_ENV='production', FINFLOW_DEMO_MODE='true',
                FINFLOW_SERVE_FRONTEND='false', CORS_ORIGINS='https://demo.vercel.app',
                FINFLOW_SUPABASE_PROJECT_REF=REF, DB_HOST='aws-1-us-east-1.pooler.supabase.com',
                DB_PORT='5432', DB_NAME='postgres', DB_USER='finflow_reader.' + REF,
                DB_PASSWORD='PRIVATE_DUMMY_SECRET', DB_SSLMODE='verify-full', **changes)


@pytest.mark.parametrize('changes,condition', [
    ({'APP_ENV': 'PRIVATE_INVALID'}, 'app_env_invalid'),
    ({'FINFLOW_DEMO_MODE': 'PRIVATE_INVALID'}, 'demo_mode_invalid'),
    ({'FINFLOW_SERVE_FRONTEND': 'PRIVATE_INVALID'}, 'serve_frontend_invalid'),
    ({'FINFLOW_DEMO_MODE': 'false'}, 'production_demo_mode_required'),
    ({'CORS_ORIGINS': 'https://demo.vercel.app/'}, 'cors_origin_invalid'),
    ({'CORS_ORIGINS': '"https://demo.vercel.app"'}, 'cors_origin_invalid'),
    ({'CORS_ORIGINS': '["https://demo.vercel.app"]'}, 'cors_origin_invalid'),
    ({'CORS_ORIGINS': 'https://user:PRIVATE_SECRET@demo.vercel.app'}, 'cors_origin_invalid'),
    ({'DB_NAME': 'PRIVATE_DB'}, 'demo_database_name_invalid'),
    ({'FINFLOW_SUPABASE_PROJECT_REF': ''}, 'supabase_project_ref_invalid'),
    ({'FINFLOW_SUPABASE_PROJECT_REF': REF + ' '}, 'supabase_project_ref_invalid'),
    ({'FINFLOW_SUPABASE_PROJECT_REF': REF.upper()}, 'supabase_project_ref_invalid'),
    ({'DB_PORT': '6543'}, 'supabase_port_invalid'),
    ({'DB_USER': 'finflow_reader'}, 'supabase_pooler_username_project_mismatch'),
    ({'DB_USER': 'finflow_reader.zyxwvutsrqponmlkjihg'}, 'supabase_pooler_username_project_mismatch'),
    ({'DB_HOST': 'PRIVATE_HOST'}, 'supabase_host_or_project_mismatch'),
    ({'DB_HOST': 'db.' + REF + '.supabase.co', 'DB_USER': ''}, 'supabase_direct_username_missing'),
])
def test_rejection_identifies_condition_without_values(monkeypatch, caplog, changes, condition):
    values = production_values()
    values.update(changes)
    monkeypatch.setattr(config, 'environment_values', lambda: values)
    with caplog.at_level(logging.ERROR, logger='uvicorn.error'), pytest.raises(RuntimeError) as caught:
        config.get_runtime_settings()
    assert str(caught.value).startswith('Invalid runtime configuration.')
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == 'runtime_configuration_invalid condition=' + condition
    assert record.exc_info is None
    assert record.stack_info is None
    assert 'PRIVATE' not in caplog.text + str(caught.value)
    assert REF not in caplog.text


@pytest.mark.parametrize('changes', [
    {}, {'CORS_ORIGINS': ' https://demo.vercel.app , https://other.vercel.app '},
    {'DB_HOST': 'db.' + REF + '.supabase.co', 'DB_USER': 'finflow_reader'},
])
def test_valid_production_dummy_environment(monkeypatch, caplog, changes):
    values = production_values()
    values.update(changes)
    monkeypatch.setattr(config, 'environment_values', lambda: values)
    settings = config.get_settings()
    assert settings.sslmode == 'verify-full'
    assert not caplog.records


def test_process_environment_overrides_dotenv(monkeypatch):
    monkeypatch.setattr(config, 'dotenv_values', lambda path: {'FINFLOW_SUPABASE_PROJECT_REF': 'PRIVATE_FILE_REF'})
    monkeypatch.setenv('FINFLOW_SUPABASE_PROJECT_REF', REF)
    assert config.environment_values()['FINFLOW_SUPABASE_PROJECT_REF'] == REF
