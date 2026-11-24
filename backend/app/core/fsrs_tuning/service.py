import math, logging, datetime
import asyncpg
from app.core.fsrs_tuning import data_extractor, optimizer_runner
from app.db import repository
from app.config import settings

logger = logging.getLogger(__name__)


class FsrsTuningService:
    async def run_fsrs_tuning_job(self, user_id: str, pool: asyncpg.Pool) -> dict:
        import asyncio
        dataset = await data_extractor.extract_and_format_training_data_async(pool, user_id)
        n = dataset.total_reviews
        if n < settings.FSRS_TUNING_THRESHOLD:
            return {"status": "cold_start", "review_count": n, "threshold": settings.FSRS_TUNING_THRESHOLD}
        try:
            weights, rmse = await asyncio.to_thread(optimizer_runner.run_optimizer, dataset)
            return {"status": "success", "weights": weights, "rmse": rmse, "review_count": n}
        except Exception as e:
            logger.error(f"FSRS tuning error for {user_id}: {e}", exc_info=True)
            return {"status": "error", "message": str(e), "review_count": n}

    async def apply_and_cache_weights(
        self, pool: asyncpg.Pool, user_id: str, weights: list[float], rmse: float, review_count: int
    ):
        if len(weights) != 17:
            raise ValueError(f"Expected 17 weights, got {len(weights)}")
        for w in weights:
            if not isinstance(w, (int, float)) or not math.isfinite(w):
                raise ValueError(f"Invalid weight: {w}")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await repository.update_profile(
            pool, user_id,
            fsrs_custom_weights=weights,
            fsrs_tuning={"last_run_at": now, "last_rmse": rmse, "review_count_at_last_run": review_count},
        )
