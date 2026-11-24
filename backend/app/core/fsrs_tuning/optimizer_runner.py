import tempfile
import math
import os
import datetime
from typing import List, Tuple
from app.core.fsrs_tuning.data_extractor import TrainingDataset

def run_optimizer(dataset: TrainingDataset) -> Tuple[List[float], float]:
    import fsrs_optimizer
    if not dataset.items or dataset.total_reviews == 0:
        raise ValueError("Dataset is empty; cannot run optimizer.")
    
    with tempfile.NamedTemporaryFile(suffix=".tsv", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write("card_id\treview_time\trating\treview_state\n")
        for i, item in enumerate(dataset.items):
            current_time = datetime.datetime(2026, 1, 1)
            for rev in item.reviews:
                current_time += datetime.timedelta(days=rev.delta_t)
                time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
                tmp.write(f"{i}\t{time_str}\t{rev.rating}\t{rev.review_state}\n")
        tmp_name = tmp.name

    try:
        optimizer = fsrs_optimizer.Optimizer()
        optimizer.anki_extract(tmp_name)
        optimizer.define_model()
        optimizer.pretrain(verbose=False)
        optimizer.train(verbose=False)
        weights = list(optimizer.w)
        if len(weights) != 17:
            raise ValueError(f"Optimizer returned {len(weights)} weights, expected 17")
        for w in weights:
            if not isinstance(w, (int, float)) or not math.isfinite(w):
                raise ValueError(f"Invalid optimizer weight: {w}")
        rmse = getattr(optimizer, "rmse", 0.0)
        if not math.isfinite(rmse):
            rmse = 0.0
        return weights, float(rmse)
    finally:
        try:
            os.remove(tmp_name)
        except Exception:
            pass
