"""Diagnostics never expose driver messages, statements, or connection data."""
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config import RuntimeSettings
from app.database import get_db
from app.db_diagnostics import log_database_failure
from app.main import create_app


class DriverFailure(Exception):
    def __init__(self, state, message):
        super().__init__(message)
        self.sqlstate = state


def failure(state=None, message='PRIVATE_PASSWORD postgresql://PRIVATE_CONNECTION PRIVATE_HOST'):
    return OperationalError('PRIVATE_SQL', {'password': 'PRIVATE_PARAMETER'}, DriverFailure(state, message))


@pytest.mark.parametrize('state,message,category', [
    ('28P01', 'private', 'authentication'),
    ('42501', 'private', 'permissions'),
    ('42P01', 'private', 'missing_relation_or_search_path'),
    ('3D000', 'private', 'database_not_found'),
    ('53300', 'private', 'connection_limit'),
    (None, 'certificate verify failed PRIVATE', 'tls_or_certificate'),
    (None, 'Tenant or user not found PRIVATE', 'authentication_or_pooler_identity'),
    (None, 'could not translate host name PRIVATE', 'dns'),
    (None, 'connection timed out PRIVATE', 'network_or_timeout'),
    ('08006', 'private', 'connection_failure'),
    (None, 'PRIVATE', 'unclassified_database_error'),
])
def test_safe_categories(caplog, state, message, category):
    with caplog.at_level(logging.ERROR, logger='uvicorn.error'):
        log_database_failure(failure(state, message), 'connect')
    record = caplog.records[-1]
    assert 'stage=connect' in record.getMessage()
    assert 'exception_class=OperationalError' in record.getMessage()
    assert 'category=' + category in record.getMessage()
    assert 'PRIVATE' not in record.getMessage()
    assert record.exc_info is None
    assert record.stack_info is None


def test_untrusted_fields_and_messages_never_logged(caplog):
    with caplog.at_level(logging.ERROR, logger='uvicorn.error'):
        log_database_failure(failure('PRIVATE\ninjected'), 'PRIVATE_STAGE')
    message = caplog.records[-1].getMessage()
    assert 'PRIVATE' not in message
    assert 'sqlstate=none' in message
    assert 'stage=operation' in message
    assert '\n' not in message


@pytest.mark.parametrize('failed_stage', ['connect', 'readiness_probe', 'schema_revision'])
def test_readiness_logs_correct_stage_and_generic_response(caplog, failed_stage):
    app = create_app(RuntimeSettings())
    class FakeSession:
        calls = 0
        def connection(self):
            if failed_stage == 'connect':
                raise failure('28P01')
        def execute(self, statement):
            self.calls += 1
            if self.calls == (1 if failed_stage == 'readiness_probe' else 2):
                raise failure('42501')
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ['0003']))
    def isolated_db():
        yield FakeSession()
    app.dependency_overrides[get_db] = isolated_db
    with caplog.at_level(logging.ERROR, logger='uvicorn.error'), TestClient(app) as client:
        response = client.get('/api/readiness?PRIVATE_QUERY=PRIVATE_VALUE')
    assert response.status_code == 503
    assert response.json() == {'detail': 'Database operation unavailable'}
    records = [r for r in caplog.records if r.name == 'uvicorn.error']
    assert len(records) == 1
    assert 'stage=' + failed_stage in records[0].getMessage()
    assert 'PRIVATE' not in records[0].getMessage()
