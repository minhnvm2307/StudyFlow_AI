# StudyFlow AI — Scheduling System Architecture & Logic

This document describes the core scheduling logic of StudyFlow AI, combining constraint satisfaction optimization (**Google OR-Tools CP-SAT**) with spaced repetition spacing (**FSRS-6**) and Bayesian Knowledge Tracing (**BKT**).

---

## 1. Core Scheduling Trigger
The schedule is rebuilt dynamically (Lazy Rebuild) when the plan is marked "dirty". Trigger events include:
- Creating or updating a subject (e.g. changing study mode, priority, or exam date).
- Completing a study session (diagnostic quiz or practice session).
- Changing user study preferences (daily study budget, study days).
- Automatic daily sweeps that flag past uncompleted tasks as `missed`.

The entry point is `build_unified_schedule(user_id)` which runs under a PostgreSQL advisory lock per user to prevent concurrent conflicts.

---

## 2. The Multi-Subject Scheduling Pipeline

```
                     ┌───────────────────────────────────┐
                     │     Unified Scheduling Trigger    │
                     └─────────────────┬─────────────────┘
                                       ▼
                     ┌───────────────────────────────────┐
                     │       Step 0: Sweep Missed        │
                     │  Past ready tasks -> 'missed' status│
                     └─────────────────┬─────────────────┘
                                       ▼
                     ┌───────────────────────────────────┐
                     │      Step 1: Compute Horizon      │
                     │  horizon = min(exam_dates) or 14d │
                     └─────────────────┬─────────────────┘
                                       ▼
                     ┌───────────────────────────────────┐
                     │    Phase 1: CP-SAT Coverage       │
                     │  - schedules all unlearned topics │
                     │  - objective: load leveling       │
                     └─────────────────┬─────────────────┘
                                       ▼
                     ┌───────────────────────────────────┐
                     │    Phase 2: FSRS Greedy Fill      │
                     │  - fills remaining budget with    │
                     │    due reviews (cross-subject)    │
                     └─────────────────┬─────────────────┘
                                       ▼
                     ┌───────────────────────────────────┐
                     │      Ghi DB: study_tasks          │
                     └───────────────────────────────────┘
```

### Step 0: Sweep Missed
Before any schedule calculations, the database queries all past tasks that are still in `ready` state. They are marked `missed`.
- **New Topics**: Since `is_learned` remains `False`, they will be automatically re-added to the unlearned pool for rescheduling.
- **Review Topics**: Their FSRS due date remains in the past, meaning they will be automatically queued in Phase 2.

### Step 1: Compute Rolling Horizon
The scheduling horizon (in days) is calculated as:
```python
horizon = min(all_active_subject_exam_dates) - today
```
If no subjects have exam dates, the horizon defaults to **14 days**.

### Step 2: Phase 1 — CP-SAT Coverage & Leveling
Google OR-Tools CP-SAT schedules all unlearned topics (`is_learned = False` and `awaiting_diagnostic = False`) across all subjects.

- **Completion Constraint**: Every unlearned topic must be scheduled exactly once within the horizon.
- **Precedence Constraint**: Linear order is maintained within each subject based on `order_idx`. (Topic *A* must be scheduled on a day strictly before Topic *B* if $order\_idx_A < order\_idx_B$).
- **Deadline Constraint**: A topic must be scheduled before the exam date of the subject it belongs to.
- **Budget Constraint**: The total study duration of topics assigned to day $d$ cannot exceed:
  $$\text{daily\_budget} + \text{slack}_d$$
  where $\text{slack}_d \le 20\%$ of the daily budget.
- **Objective (Target-based Leveling)**:
  Instead of left-justifying study tasks (which causes cramping), the solver distributes study load evenly to match the average daily target:
  $$\text{target\_load} = \frac{\sum \text{cost of unlearned topics}}{\text{number of valid study days}}$$
  The objective function minimizes:
  $$\sum_d |\text{load}_d - \text{target\_load}| + \text{penalty\_weight} \times \sum_d \text{slack}_d$$
  If no valid schedule satisfies these rules (e.g. exam is too close), the solver returns `"status": "infeasible"`.

### Step 3: Phase 2 — Spaced Repetition Greedy Fill
For each day in the horizon, any remaining study budget (after Phase 1 allocation) is filled with due reviews from the global pool of learned topics:

1. **Query Due Reviews**: Get all learned topics where `fsrs_due_date <= target_date`.
2. **Sort by Cross-Subject Urgency**: Sort due reviews using a weighted score:
   $$\text{Urgency} = 0.25 \times \text{Weakness} + 0.20 \times \text{Exam proximity} + 0.25 \times \text{Priority boost} + 0.30 \times \text{Forgetting risk}$$
   - *Weakness*: $1 - \text{BKT mastery}$.
   - *Exam proximity*: $1 / \text{days remaining until exam}$.
   - *Priority boost*: $2.0$ if the subject is marked priority, else $1.0$.
   - *Forgetting risk*: $1 - \text{FSRS predicted retention}$.
3. **Simulate spaced learning**: When a review task is assigned to day $d$, FSRS calculates its next stability in memory (assuming a "Good" rating outcome). The topic's virtual due date is updated to:
   $$\text{due\_date} = d + \text{stability}$$
   This removes it from the queue for subsequent days in the scheduling window.

---

## 3. Practice Submission & State Update
When a user completes a quiz question session:
1. **Bayesian Knowledge Tracing (BKT)**: Updates the topic mastery score based on correct/incorrect answers.
2. **FSRS Spaced Repetition**: Updates the scheduling parameters (difficulty, stability, retrievability, due date) based on the user's selected rating ("Again", "Hard", "Good", "Easy").
3. **Transition to Learned**: If the task was a `NEW` task, the topic is marked `is_learned = True` in the database, moving it permanently into the Phase 2 review pool.
4. **Mark Plan Dirty**: The plan is marked dirty so the schedule is rebuilt to reflect updated mastery and review intervals.
