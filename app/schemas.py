import uuid

from pydantic import BaseModel


class Credentials(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str


class AuthResponse(BaseModel):
    user: UserOut
    token: str
