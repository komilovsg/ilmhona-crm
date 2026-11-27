"""Who pays for a cohort's students: the one place that decides it.

- платный: every student pays (as before); no donors.
- бесплатный: price 0, nobody pays; no donors.
- донор: every student is paid for by one of the cohort's donors; with one donor it is set by
  itself, with several it must be chosen.
- смешанный: a price and donors; each student either pays or is paid for by one donor.

A donor-funded student owes nothing and no payment is taken for them (`app.metrics.money`).
Moving a student from a donor to paying themself sets `pays_from`: the debt counts from that
month. Owner decisions: one donor per enrollment, no partial cover, no quotas, the donor's money
is not tracked.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.donors.errors import (
    DONOR_ARCHIVED,
    DONOR_IN_USE,
    DONOR_NOT_IN_COHORT,
    DONOR_REQUIRED,
    FUNDING_DONORS_INVALID,
    FUNDING_HAS_PAYERS,
)
from app.models import Cohort, CohortDonor, Donor, Enrollment

PAID, FREE, DONOR, MIXED = "платный", "бесплатный", "донор", "смешанный"
FUNDINGS = (PAID, FREE, DONOR, MIXED)
WITH_DONORS = (DONOR, MIXED)


async def cohort_donors(
    db: AsyncSession, cohort_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """The donors of each cohort, by name: [{id, name, archived}]."""
    out: dict[uuid.UUID, list[dict[str, Any]]] = {c: [] for c in cohort_ids}
    if not cohort_ids:
        return out
    rows = await db.execute(
        select(CohortDonor.cohort_id, Donor.id, Donor.name, Donor.archived)
        .join(Donor, Donor.id == CohortDonor.donor_id)
        .where(CohortDonor.cohort_id.in_(cohort_ids))
        .order_by(Donor.name)
    )
    for cid, did, name, archived in rows.all():
        out[cid].append({"id": did, "name": name, "archived": archived})
    return out


async def check_new_donors(db: AsyncSession, donor_ids: Sequence[uuid.UUID]) -> None:
    """Donors being added to a cohort exist (404) and are not archived."""
    if not donor_ids:
        return
    found = dict(
        (await db.execute(select(Donor.id, Donor.archived).where(Donor.id.in_(donor_ids)))).all()
    )
    if len(found) != len(set(donor_ids)):
        raise DomainError(DONOR_NOT_IN_COHORT).for_field("donor_ids", "donor_not_found")
    if any(found.values()):
        raise DomainError(DONOR_ARCHIVED).for_field("donor_ids", "donor_archived")


def check_funding(funding: str, donor_ids: Sequence[uuid.UUID]) -> None:
    if (funding in WITH_DONORS) != bool(donor_ids):
        raise DomainError(FUNDING_DONORS_INVALID).for_field("donor_ids", "funding_donors_invalid")


async def set_cohort_funding(
    db: AsyncSession, cohort: Cohort, funding: str, donor_ids: Sequence[uuid.UUID]
) -> dict[str, Any]:
    """Apply a cohort's funding and donors (call with the cohort row locked, after a flush of a
    new cohort). Returns what changed for the students: {"auto": n} when the students who paid
    themselves were all given the one donor of a «донор» cohort."""
    donor_ids = list(dict.fromkeys(donor_ids))
    check_funding(funding, donor_ids)
    current = set(
        (
            await db.execute(select(CohortDonor.donor_id).where(CohortDonor.cohort_id == cohort.id))
        ).scalars()
    )
    await check_new_donors(db, [d for d in donor_ids if d not in current])
    removed = current - set(donor_ids)
    if removed:
        used = (
            await db.scalar(
                select(func.count())
                .select_from(Enrollment)
                .where(Enrollment.cohort_id == cohort.id, Enrollment.donor_id.in_(removed))
            )
        ) or 0
        if used:
            raise DomainError(DONOR_IN_USE, count=used)
        await db.execute(
            delete(CohortDonor).where(
                CohortDonor.cohort_id == cohort.id, CohortDonor.donor_id.in_(removed)
            )
        )
    for d in donor_ids:
        if d not in current:
            db.add(CohortDonor(cohort_id=cohort.id, donor_id=d))
    cohort.funding = funding
    if funding == FREE:
        cohort.price_month = Decimal("0.00")
    await db.flush()
    note: dict[str, Any] = {}
    if funding == DONOR:
        payers = (
            await db.scalar(
                select(func.count())
                .select_from(Enrollment)
                .where(Enrollment.cohort_id == cohort.id, Enrollment.donor_id.is_(None))
            )
        ) or 0
        if payers and len(donor_ids) > 1:
            raise DomainError(FUNDING_HAS_PAYERS, count=payers)
        if payers:
            await db.execute(
                update(Enrollment)
                .where(Enrollment.cohort_id == cohort.id, Enrollment.donor_id.is_(None))
                .values(donor_id=donor_ids[0])
            )
            note["auto"] = payers
    return note


async def enrollment_donor(
    db: AsyncSession, cohort: Cohort, requested: uuid.UUID | None
) -> uuid.UUID | None:
    """The donor of a new enrollment: the one asked for (must fund the cohort), the only donor of
    a «донор» cohort, or None (pays themself / free)."""
    donors = [
        d
        for (d,) in (
            await db.execute(select(CohortDonor.donor_id).where(CohortDonor.cohort_id == cohort.id))
        ).all()
    ]
    if requested is not None:
        if cohort.funding not in WITH_DONORS or requested not in donors:
            raise DomainError(DONOR_NOT_IN_COHORT).for_field("donor_id", "donor_not_in_cohort")
        return requested
    if cohort.funding == DONOR:
        if len(donors) == 1:
            return donors[0]
        raise DomainError(DONOR_REQUIRED).for_field("donor_id", "donor_required")
    return None


async def donor_names(db: AsyncSession, ids: Sequence[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await db.execute(select(Donor.id, Donor.name).where(Donor.id.in_(wanted)))
    return dict(rows.all())


def funding_label(cohort_funding: str, donor_name: str | None) -> str:
    """How a student is paid for, in words: «Платит сам», «Донор: X», «Бесплатно»."""
    if donor_name:
        return f"Донор: {donor_name}"
    return "Бесплатно" if cohort_funding == FREE else "Платит сам"
