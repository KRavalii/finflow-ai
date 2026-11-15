"""Resolve workspace scope before reading or converting any financial rows."""
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import inspect, select

from .models import Profile

ProfileScope = int | Literal['all'] | None


def profiles_available(db):
    return inspect(db.connection()).has_table('profiles')


def resolve_profile(db, profile_id: ProfileScope = None, *, write=False):
    if not profiles_available(db):
        if profile_id is not None:
            raise HTTPException(409, detail={'code': 'profiles_migration_required',
                                            'message': 'Profiles require approved migration 0003.'})
        return None  # Pre-0003 compatibility: the sole existing workspace.
    if profile_id == 'all':
        if write:
            raise HTTPException(422, 'Select one active profile to change transactions')
        return None
    statement = select(Profile).where(Profile.is_default.is_(True) if profile_id is None else Profile.id == profile_id)
    if write:
        statement = statement.with_for_update()
    profile = db.scalar(statement)
    if profile is None:
        raise HTTPException(404, 'Profile not found')
    if write and profile.archived_at is not None:
        raise HTTPException(409, 'Archived profiles are read-only')
    return profile


def scope_statement(statement, model, profile):
    return statement.where(model.profile_id == profile.id) if profile is not None else statement
