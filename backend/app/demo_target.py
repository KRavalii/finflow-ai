"""Shared allowlist for explicitly selected public-demo database targets."""
import re


class DemoTargetError(ValueError):
    """Fixed diagnostic code only; never include configuration values."""


def validate_demo_target(name, host=None, user=None, port=None, project_ref=None):
    if name == 'finflow_demo':
        return
    if name != 'postgres':
        raise DemoTargetError('demo_database_name_invalid')
    if not re.fullmatch(r'[a-z0-9]{20}', project_ref or ''):
        raise DemoTargetError('supabase_project_ref_invalid')
    direct = host == f'db.{project_ref}.supabase.co' and bool(user)
    session = (
        bool(re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com', host or ''))
        and bool(re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*\.' + re.escape(project_ref), user or ''))
    )
    if str(port or 5432) != '5432':
        raise DemoTargetError('supabase_port_invalid')
    if not (direct or session):
        pooler_host = bool(re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com', host or ''))
        if pooler_host:
            raise DemoTargetError('supabase_pooler_username_project_mismatch')
        if host == f'db.{project_ref}.supabase.co':
            raise DemoTargetError('supabase_direct_username_missing')
        raise DemoTargetError('supabase_host_or_project_mismatch')
