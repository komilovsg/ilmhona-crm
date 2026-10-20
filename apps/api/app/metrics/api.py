"""`GET /api/v1/metrics/education`: the education numbers for the user's scope."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth.deps import Principal, require_csrf_header
from app.core.db import DB
from app.education.scope import cohort_filters, require_any, student_filters
from app.metrics import education_summary

router = APIRouter(
    prefix="/api/v1/metrics", tags=["metrics"], dependencies=[Depends(require_csrf_header)]
)


@router.get("/education")
async def education(
    p: Annotated[Principal, require_any("cohorts", "students")], db: DB
) -> dict[str, Any]:
    return await education_summary(db, cohort_filters(p), student_filters(p))
