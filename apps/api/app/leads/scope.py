"""Who sees which sales rows. Branch scope applies; the instructor role has no access to leads or
campaigns whatever the rights matrix says (it gets 403 here, like it cannot write students)."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import ColumnElement

from app.auth.deps import CurrentUser, Principal
from app.core.errors import FORBIDDEN, DomainError
from app.education.scope import is_instructor
from app.models import Campaign, Lead
from app.permissions import allows


def reader(section: str) -> object:
    async def dependency(p: CurrentUser) -> Principal:
        if not allows(p.level(section), "view") or is_instructor(p):
            raise DomainError(FORBIDDEN, section=section, level="view")
        return p

    return Depends(dependency)


def writer(section: str) -> object:
    async def dependency(p: CurrentUser) -> Principal:
        if not allows(p.level(section), "change") or is_instructor(p):
            raise DomainError(FORBIDDEN, section=section, level="change")
        return p

    return Depends(dependency)


LeadReader = Annotated[Principal, reader("leads")]
LeadWriter = Annotated[Principal, writer("leads")]
MarketingReader = Annotated[Principal, reader("marketing")]
MarketingWriter = Annotated[Principal, writer("marketing")]


def lead_filters(p: Principal) -> list[ColumnElement[bool]]:
    return [Lead.branch_id == p.branch_id] if p.branch_id is not None else []


def campaign_filters(p: Principal) -> list[ColumnElement[bool]]:
    return [Campaign.branch_id == p.branch_id] if p.branch_id is not None else []
