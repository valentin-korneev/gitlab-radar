from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

PreferredUsername = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class AuthorizedUserPayload(BaseModel):
    preferred_username: PreferredUsername


class AuthorizedUserCreate(AuthorizedUserPayload):
    pass


class AuthorizedUser(BaseModel):
    preferred_username: str
    source: Literal['environment', 'database']
    is_admin: bool
    is_blocked: bool


class AuthorizedUserUpdate(AuthorizedUserPayload):
    is_admin: bool
    is_blocked: bool
