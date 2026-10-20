from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.attendance.api import router as attendance_router
from app.audit.api import router as audit_router
from app.auth.api import router as auth_router
from app.branches.api import router as branches_router
from app.campaigns.api import router as campaigns_router
from app.cohorts.api import router as cohorts_router
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.core.proxy import ProxySecretRequired
from app.employment.api import router as employment_router
from app.graduates.api import router as graduates_router
from app.instructors.api import router as instructors_router
from app.leads.api import router as leads_router
from app.metrics.api import router as metrics_router
from app.payments.api import router as payments_router
from app.reports.api import router as reports_router
from app.roles.api import router as roles_router
from app.rooms.api import router as rooms_router
from app.salaries.api import router as salaries_router
from app.students.api import router as students_router
from app.users.api import router as users_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.check()
    yield


app = FastAPI(
    title="ilmhona CRM",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.api_docs else None,
    openapi_url="/api/openapi.json" if settings.api_docs else None,
    redoc_url=None,
)
install_error_handlers(app)
if settings.proxy_secrets:
    app.add_middleware(ProxySecretRequired, secrets=settings.proxy_secrets)
for router in (
    auth_router,
    users_router,
    roles_router,
    audit_router,
    branches_router,
    rooms_router,
    cohorts_router,
    attendance_router,
    students_router,
    metrics_router,
    payments_router,
    instructors_router,
    salaries_router,
    leads_router,
    campaigns_router,
    reports_router,
    graduates_router,
    employment_router,
):
    app.include_router(router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
