from fastapi import APIRouter
from app.api.routes.compat import router as compat_router
from app.api.routes.state import router as state_router
from app.api.routes.auth import router as auth_router
from app.api.routes.subjects import router as subjects_router
from app.api.routes.documents import router as documents_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.exam import router as exam_router
from app.api.routes.misc import router as misc_router
from app.api.routes.fsrs_tuning import router as fsrs_tuning_router

router = APIRouter()

for child_router in (
    compat_router,
    state_router,
    auth_router,
    subjects_router,
    documents_router,
    sessions_router,
    exam_router,
    misc_router,
    fsrs_tuning_router,
):
    router.routes.extend(child_router.routes)
