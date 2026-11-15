"""Default profile for isolated metadata-created test schemas only.

Production profile creation belongs exclusively to migration 0003.
"""
from sqlalchemy import event
from app.models import Profile


@event.listens_for(Profile.__table__, 'after_create')
def seed_test_default(target, connection, **kwargs):
    connection.execute(target.insert().values(name='My Profile', is_default=True))
