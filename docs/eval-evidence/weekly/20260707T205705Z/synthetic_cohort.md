# Synthetic Eval Cohort

Generated at: `2026-07-07T20:57:12.054116+00:00`
Prefix: `synthetic-eval`
History window: `28` days

## Counts

- `users`: 6
- `courses`: 12
- `topics`: 48
- `sources`: 12
- `chunks`: 48
- `tasks`: 123
- `mastery_events`: 4380
- `review_logs`: 122
- `quizzes`: 12
- `flashcards`: 24
- `chat_threads`: 12

## Offline Metrics

- `RMSE`: 0.4863
- `Brier`: 0.2365
- `AUC`: 0.6922
- `Avg predicted`: 0.4795
- `Avg actual`: 0.6466
- `Calibration gap`: 0.1671

## Scheduler Metrics

- `Total courses`: 12
- `Coverage warning count`: 0
- `Over-budget warning count`: 0
- `Over-budget warning rate`: 0.0

## Avg Profile Metrics

- `knowledgeConsistency`: 85.5
- `retentionReliability`: 33.33
- `personalCalibrationScore`: 91
- `calibrationGap`: 9
- `engagementConfidence`: 23.67

## Source Breakdown

| Source | Count | RMSE | Avg Predicted | Avg Actual |
| --- | ---: | ---: | ---: | ---: |
| entry_diagnostic_quiz | 1800 | 0.509 | 0.4254 | 0.625 |
| system_quiz | 1020 | 0.4701 | 0.5357 | 0.6657 |
| workspace_quiz | 1560 | 0.4698 | 0.5053 | 0.659 |

## Sample Users

| Username | Password | Persona | Courses | Events | Consistency | Calibration | Retention |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| synthetic-eval-steady-01 | synthetic-2026 | Steady Achiever | 2 | 858 | 81 | 81 | 100 |
| synthetic-eval-sprint-02 | synthetic-2026 | Last-Minute Sprinter | 2 | 858 | 88 | 94 | 0 |
| synthetic-eval-overloaded-03 | synthetic-2026 | Overloaded Struggler | 2 | 693 | 91 | 99 | 0 |
| synthetic-eval-steady-04 | synthetic-2026 | Steady Achiever | 2 | 702 | 79 | 79 | 100 |
| synthetic-eval-sprint-05 | synthetic-2026 | Last-Minute Sprinter | 2 | 702 | 86 | 97 | 0 |
| synthetic-eval-overloaded-06 | synthetic-2026 | Overloaded Struggler | 2 | 567 | 88 | 96 | 0 |
