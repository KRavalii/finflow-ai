from functools import lru_cache

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from .config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True,
                         hide_parameters=True, connect_args={"connect_timeout": 5})


def get_db(request: Request):
    request.state.database_stage = 'session_setup'
    with Session(get_engine()) as session:
        try:
            request.state.database_stage = 'operation'
            yield session
        except Exception:
            session.rollback()
            raise
