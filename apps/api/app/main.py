from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.audit.api import router as audit_router
from app.auth.api import router as auth_router
from app.branches.api import router as branches_router
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.roles.api import router as roles_router
from app.users.api import router as users_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.check()
    yield


app = FastAPI(
    title="ilmhona CRM", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json"
)
install_error_handlers(app)
for router in (auth_router, users_router, roles_router, audit_router, branches_router):
    app.include_router(router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
