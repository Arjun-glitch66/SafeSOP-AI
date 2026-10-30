"""Shared request vocabularies and review-state rules."""


# Version states: draft -> needs_revision | approved | rejected. Approved versions are
# locked; any further review is refused with 409. Changes go into a new version.
REVIEW_DECISIONS = {"approved", "rejected", "needs_revision"}


LOCKED_STATUSES = ("approved",)


LOCKED_DETAIL = "This version is approved and locked. Generate a new version to make changes."
