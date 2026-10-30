"""Shared request bodies, vocabularies and review-state rules."""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class NewUser(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(max_length=200)
    role: str


# Version states: draft -> needs_revision | approved | rejected. Approved versions are
# locked; any further review is refused with 409. Changes go into a new version.
REVIEW_DECISIONS = {"approved", "rejected", "needs_revision"}


LOCKED_STATUSES = ("approved",)


LOCKED_DETAIL = "This version is approved and locked. Generate a new version to make changes."
