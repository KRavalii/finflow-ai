from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Name


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Name | None = None
    archived: bool | None = None

    @model_validator(mode='after')
    def supplied_values(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Supply a name or archived status; null is not allowed')
        return self


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    created_at: datetime
    is_default: bool
    archived_at: datetime | None
