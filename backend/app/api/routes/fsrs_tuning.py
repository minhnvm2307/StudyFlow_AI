import asyncpg
from fastapi import APIRouter, Depends, Query

from app.api.deps import current_user_id
from app.config import settings
from app.core.fsrs_tuning.service import FsrsTuningService
from app.db import repository
from app.db.pg_pool import get_pool

router = APIRouter()
tuning_service = FsrsTuningService()


def _uid() -> str:
    return current_user_id()


@router.get("/api/fsrs/tuning/status")
async def get_tuning_status(
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    profile = await repository.get_profile(pool, uid)
    logs = await repository.get_review_logs(pool, uid)
    return {
        "status": "success",
        "reviewCount": len(logs),
        "threshold": settings.FSRS_TUNING_THRESHOLD,
        "lastRunAt": profile.fsrs_tuning.last_run_at if profile else None,
        "lastRmse": profile.fsrs_tuning.last_rmse if profile else None,
        "reviewCountAtLastRun": profile.fsrs_tuning.review_count_at_last_run if profile else 0,
    }


@router.post("/api/fsrs/tuning/run")
async def run_tuning(
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = _uid()
    result = await tuning_service.run_fsrs_tuning_job(uid, pool)
    if result.get("status") == "success":
        await tuning_service.apply_and_cache_weights(
            pool,
            uid,
            result["weights"],
            result["rmse"],
            result["review_count"],
        )
        result["applied"] = True
        await repository.set_plan_dirty(pool, uid, True)
    return {"status": result.get("status"), **{key: value for key, value in result.items() if key != "status"}}
