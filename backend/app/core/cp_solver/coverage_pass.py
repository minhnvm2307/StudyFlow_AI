"""CP-SAT Coverage Pass (Phase 1 of the Hybrid Scheduler v5)."""
from __future__ import annotations

from ortools.sat.python import cp_model

from app.config import settings


def solve_coverage_pass(
    global_pool_new: list[dict],
    daily_budget: int,
    horizon: int,
    study_days_map: list[bool],
    reserved_minutes_by_day: dict[int, int] | None = None,
    relax_deadlines: bool = False,
) -> dict:
    """
    Assign every unlearned topic across all subjects to exactly one study day, respecting:
    - Subject-specific order index precedence constraint
    - Subject-specific deadline constraint (exam_date)
    - Resource leveling objective (minimizing load variance around the target per day)
    - Daily budget (with up to 20% slack)
    """
    model = cp_model.CpModel()
    n = len(global_pool_new)
    reserved_minutes_by_day = reserved_minutes_by_day or {}
    max_slack = int(daily_budget * settings.CP_MAX_SLACK_PERCENT)
    if n == 0:
        return {"status": "success", "schedule": {}, "is_over_budget": False}

    valid_days = [
        d for d in range(horizon)
        if d < len(study_days_map)
        and study_days_map[d]
        and int(reserved_minutes_by_day.get(d, 0)) <= daily_budget + max_slack
    ]

    if not valid_days:
        return {"status": "error", "message": "No valid study days"}

    allowed_days_by_topic = [
        _allowed_days_for_topic(topic, valid_days)
        for topic in global_pool_new
    ]
    if any(not days for days in allowed_days_by_topic):
        return {"status": "infeasible"}

    # x[i, d] = 1 if topic i assigned to day d
    x = {
        (i, d): model.NewBoolVar(f"t{i}_d{d}")
        for i in range(n)
        for d in allowed_days_by_topic[i]
    }
    
    # day_assigned[i] = day index topic i is assigned to
    day_assigned = [model.NewIntVar(0, horizon - 1, f"day_{i}") for i in range(n)]
    
    slacks = {d: model.NewIntVar(0, max_slack, f"slack_{d}") for d in valid_days}

    # Completion + day linking
    for i in range(n):
        allowed_days = allowed_days_by_topic[i]
        model.AddExactlyOne([x[(i, d)] for d in allowed_days])
        model.Add(
            day_assigned[i] == cp_model.LinearExpr.WeightedSum(
                [x[(i, d)] for d in allowed_days], allowed_days
            )
        )
        
        # Per-subject deadline
        deadline = global_pool_new[i].get("subject_deadline_day")
        if not relax_deadlines and deadline is not None and deadline < horizon:
            model.Add(day_assigned[i] <= max(0, deadline - 1))

    # Per-subject precedence (order_idx linear in same subject)
    by_subject: dict[str, list[int]] = {}
    for i, t in enumerate(global_pool_new):
        by_subject.setdefault(t.get("subject_id", "subject-mock"), []).append(i)
        
    for subj_id, idxs in by_subject.items():
        idxs.sort(key=lambda idx: global_pool_new[idx]["order_idx"])
        for a, b in zip(idxs, idxs[1:]):
            model.Add(day_assigned[a] <= day_assigned[b])

    # Budget + slack
    load_exprs = {}
    for d in valid_days:
        load_exprs[d] = cp_model.LinearExpr.WeightedSum(
            [x[(i, d)] for i in range(n) if (i, d) in x],
            [global_pool_new[i]["cost_mins"] for i in range(n) if (i, d) in x]
        )
        model.Add(load_exprs[d] + int(reserved_minutes_by_day.get(d, 0)) <= daily_budget + slacks[d])

    # Resource leveling
    total_cost = sum(t["cost_mins"] for t in global_pool_new)
    reserved_total = sum(int(reserved_minutes_by_day.get(d, 0)) for d in valid_days)
    combined_target = round((total_cost + reserved_total) / len(valid_days))
    diff_bound = max(1, daily_budget + max_slack + total_cost + reserved_total)
    diffs = {}
    for d in valid_days:
        diffs[d] = model.NewIntVar(0, diff_bound, f"diff_{d}")
        reserved = int(reserved_minutes_by_day.get(d, 0))
        model.Add(diffs[d] >= load_exprs[d] + reserved - combined_target)
        model.Add(diffs[d] >= combined_target - load_exprs[d] - reserved)

    penalty_weight = max(1, horizon // max(1, n))
    target_penalties = []
    target_penalty_weights = []
    for i, topic in enumerate(global_pool_new):
        target = topic.get("target_day_offset")
        if target is None:
            continue
        target = max(0, min(horizon - 1, int(target)))
        penalty = model.NewIntVar(0, horizon, f"target_penalty_{i}")
        model.Add(penalty >= day_assigned[i] - target)
        model.Add(penalty >= target - day_assigned[i])
        target_penalties.append(penalty)
        target_penalty_weights.append(max(1, int(topic.get("target_penalty_weight") or 3)))

    model.Minimize(
        cp_model.LinearExpr.Sum(list(diffs.values()))
        + cp_model.LinearExpr.WeightedSum(list(slacks.values()), [penalty_weight] * len(slacks))
        + cp_model.LinearExpr.WeightedSum(target_penalties, target_penalty_weights)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = settings.CP_SOLVER_TIMEOUT_SECONDS
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": "infeasible"}

    schedule = {}
    total_slack = 0
    for d in valid_days:
        assigned = [global_pool_new[i]["id"] for i in range(n) if (i, d) in x and solver.Value(x[(i, d)]) == 1]
        used_slack = solver.Value(slacks[d])
        total_slack += used_slack
        if assigned:
            schedule[d] = {
                "new_topics": assigned,
                "budget_used": sum(
                    global_pool_new[i]["cost_mins"]
                    for i in range(n) if (i, d) in x and solver.Value(x[(i, d)]) == 1
                ),
            }
            
    return {"status": "success", "schedule": schedule, "is_over_budget": total_slack > 0}


def _allowed_days_for_topic(topic: dict, valid_days: list[int]) -> list[int]:
    allowed = topic.get("allowed_day_offsets")
    if allowed is None:
        return valid_days
    allowed_set = {int(day) for day in allowed}
    return [day for day in valid_days if day in allowed_set]
