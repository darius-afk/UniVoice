from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PromoteDecision:
    allowed: bool
    new_target_audience: str | None = None
    reason: str | None = None


def normalize_roles(roles: Iterable[str] | None) -> set[str]:
    return {str(r).strip() for r in (roles or []) if str(r).strip()}


def can_view_poll(target_audience: str, *, is_logged_in: bool, roles: Iterable[str] | None) -> bool:
    """Visibility rules used by index page.

    - 'all' is visible to everyone
    - otherwise user must be logged in and have the matching role
    - 'admin' sees everything
    """
    target = (target_audience or "all").strip()
    role_set = normalize_roles(roles)

    if target == "all":
        return True

    if not is_logged_in:
        return False

    if "admin" in role_set:
        return True

    if target == "students":
        return "student" in role_set

    if target == "professors":
        return "professor" in role_set

    # Unknown target => safest is to hide
    return False


def enforce_target_audience_for_creator(submitted: str | None, roles: Iterable[str] | None) -> str:
    """Enforces who is allowed to create polls for which audience.

    Current rule from app:
    - students (i.e., not professor/admin) can only create for 'students'
    - professor/admin can create for 'all'|'students'|'professors'
    """
    target = (submitted or "all").strip()
    role_set = normalize_roles(roles)

    is_professor = "professor" in role_set
    is_admin = "admin" in role_set

    if not is_professor and not is_admin:
        return "students"

    if target not in {"all", "students", "professors"}:
        return "all"

    return target


def decide_promote(*, is_creator: bool, total_votes: int, target_audience: str) -> PromoteDecision:
    """Advanced function: promote a poll from 'students' to 'all'."""
    if not is_creator:
        return PromoteDecision(False, reason="not_creator")

    if total_votes < 3:
        return PromoteDecision(False, reason="not_enough_votes")

    if (target_audience or "").strip() != "students":
        return PromoteDecision(False, reason="not_student_target")

    return PromoteDecision(True, new_target_audience="all")
