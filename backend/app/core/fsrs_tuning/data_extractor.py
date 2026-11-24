from dataclasses import dataclass
from typing import List
import asyncpg
from app.db import repository


@dataclass
class FSRSReview:
    rating: int
    delta_t: int
    review_state: int = 0


@dataclass
class FSRSItem:
    reviews: List[FSRSReview]


@dataclass
class TrainingDataset:
    items: List[FSRSItem]
    total_reviews: int


async def extract_and_format_training_data_async(
    pool: asyncpg.Pool, user_id: str
) -> TrainingDataset:
    logs = await repository.get_review_logs(pool, user_id)
    if not logs:
        return TrainingDataset(items=[], total_reviews=0)

    grouped: dict[str, list] = {}
    for log in logs:
        grouped.setdefault(log.item_id, []).append(log)

    items: List[FSRSItem] = []
    total_reviews = 0
    for item_logs in grouped.values():
        item_logs.sort(key=lambda x: x.review_date)
        reviews = []
        for log in item_logs:
            if log.elapsed_days < 0:
                continue
            reviews.append(FSRSReview(
                rating=log.rating,
                delta_t=log.elapsed_days,
                review_state=log.review_state,
            ))
            total_reviews += 1
        if reviews:
            items.append(FSRSItem(reviews=reviews))

    return TrainingDataset(items=items, total_reviews=total_reviews)
