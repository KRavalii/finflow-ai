"""Allowlisted database diagnostics; never log exception text or SQL."""
import logging
import re

logger = logging.getLogger('uvicorn.error')
STAGES = {'session_setup', 'operation', 'connect', 'readiness_probe', 'schema_revision'}


def log_database_failure(exc, stage='operation'):
    original = getattr(exc, 'orig', None)
    state = getattr(original, 'sqlstate', None)
    state = state if isinstance(state, str) and re.fullmatch(r'[0-9A-Z]{5}', state) else 'none'
    # Inspect messages only to choose fixed labels. Never emit any message text.
    message = str(original).lower() if original is not None else ''
    if state.startswith('28'):
        category = 'authentication'
    elif state == '42501':
        category = 'permissions'
    elif state == '42P01':
        category = 'missing_relation_or_search_path'
    elif state == '3D000':
        category = 'database_not_found'
    elif state == '53300':
        category = 'connection_limit'
    elif any(term in message for term in ('certificate', 'ssl', 'tls')):
        category = 'tls_or_certificate'
    elif any(term in message for term in ('password authentication failed', 'tenant or user not found')):
        category = 'authentication_or_pooler_identity'
    elif any(term in message for term in ('could not translate host name', 'name or service not known', 'getaddrinfo')):
        category = 'dns'
    elif any(term in message for term in ('timeout', 'timed out', 'network is unreachable', 'connection refused', 'no route to host')):
        category = 'network_or_timeout'
    elif state.startswith('08'):
        category = 'connection_failure'
    else:
        category = 'unclassified_database_error'
    # Use library-defined base classes rather than arbitrary exception class names.
    exception_class = next((cls.__name__ for cls in type(exc).__mro__
                            if cls.__module__ == 'sqlalchemy.exc'), 'SQLAlchemyError')
    driver_class = type(original).__name__ if type(original).__name__ in {
        'OperationalError', 'InterfaceError', 'ProgrammingError', 'IntegrityError',
        'InvalidPassword', 'InsufficientPrivilege', 'UndefinedTable',
    } else 'unknown'
    logger.error('database_failure stage=%s exception_class=%s driver_class=%s sqlstate=%s category=%s',
                 stage if stage in STAGES else 'operation', exception_class, driver_class, state, category)
