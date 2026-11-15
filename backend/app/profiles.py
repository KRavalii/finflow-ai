from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Profile
from .profile_scope import profiles_available
from .profile_schemas import ProfileCreate, ProfileRead, ProfileUpdate

router = APIRouter(prefix='/api/profiles', tags=['profiles'])
Database = Annotated[Session, Depends(get_db)]


def require_profiles(db):
    if not profiles_available(db):
        raise HTTPException(409, detail={'code': 'profiles_migration_required',
                                        'message': 'Profiles require approved migration 0003.'})


@router.get('', response_model=list[ProfileRead])
def list_profiles(db: Database, include_archived: bool = False):
    require_profiles(db)
    statement = select(Profile).order_by(Profile.is_default.desc(), Profile.id)
    if not include_archived:
        statement = statement.where(Profile.archived_at.is_(None))
    return db.scalars(statement).all()


@router.post('', response_model=ProfileRead, status_code=201)
def create_profile(payload: ProfileCreate, db: Database):
    require_profiles(db)
    profile = Profile(name=payload.name)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.patch('/{profile_id}', response_model=ProfileRead)
def update_profile(profile_id: Annotated[int, Path(gt=0)], payload: ProfileUpdate, db: Database):
    require_profiles(db)
    # Serialize archive/restore against transaction writes in this profile.
    profile = db.scalar(select(Profile).where(Profile.id == profile_id).with_for_update())
    if profile is None:
        raise HTTPException(404, 'Profile not found')
    if payload.archived and profile.is_default:
        raise HTTPException(409, 'The default profile cannot be archived')
    if payload.name is not None:
        profile.name = payload.name
    if payload.archived is not None:
        profile.archived_at = datetime.now(timezone.utc) if payload.archived else None
    db.commit()
    db.refresh(profile)
    return profile
