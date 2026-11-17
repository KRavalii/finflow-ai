"""Shared allowlist for explicitly selected public-demo database targets."""
import re


def validate_demo_target(name, host=None, user=None, port=None, project_ref=None):
    if name == 'finflow_demo':
        return
    if name != 'postgres' or not re.fullmatch(r'[a-z0-9]{20}', project_ref or ''):
        raise ValueError('Confirm a dedicated Supabase project for postgres.')
    direct = host == f'db.{project_ref}.supabase.co' and bool(user)
    session = (
        bool(re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com', host or ''))
        and bool(re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*\.' + re.escape(project_ref), user or ''))
    )
    if str(port or 5432) != '5432' or not (direct or session):
        raise ValueError('Supabase host, session username, port and confirmed project must match.')
