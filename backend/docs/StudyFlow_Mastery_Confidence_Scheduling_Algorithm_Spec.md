# StudyFlow Adaptive Mastery, Confidence, and Spaced Scheduling Algorithm

Status: recommended algorithm specification for the current StudyFlow generation.

This document defines the recommended `C2` algorithm for StudyFlow:

- `BKT` for conceptual mastery estimation
- a separate evidence-based `confidence` model for certainty of the mastery estimate
- `FSRS` for memory spacing and retrievability
- a syllabus-aware two-pass scheduler that uses all three signals

This is an algorithm document, not an implementation guide. It describes the mathematical model, update rules, scheduling logic, and worked examples that StudyFlow should follow.

---

## 1. Why This Algorithm Is The Recommended Current Choice

StudyFlow does not need just one score per topic. It needs three different views of learner state:

1. `Mastery`: how likely the learner understands the concept.
2. `Confidence`: how certain the system is that the mastery estimate is trustworthy.
3. `Retrievability`: how likely the learner can recall the concept today.

These are related, but they are not the same thing.

The recommended `C2` architecture separates them on purpose:

- `BKT` is the right current core for mastery because it is simple, explainable, data-efficient, and already close to the current StudyFlow data model.
- `FSRS` is the right current core for spaced repetition because it is specifically built for recall scheduling and due-date prediction.
- `Confidence` should be a separate signal because a mastery estimate can be high but weakly supported, or moderate but strongly supported.

This gives StudyFlow a practical hybrid:

`mastery` answers "how much does the learner know?"

`confidence` answers "how much should the system trust that estimate?"

`FSRS` answers "when should the learner see this again for memory retention?"

That separation is more useful than collapsing everything into a single number.

---

## 2. Design Goals

The algorithm must satisfy all of the following:

1. Be explainable to engineers, product owners, and learners.
2. Work with sparse educational data, not only large-scale logs.
3. Respect the real syllabus timeline in continuous semester learning.
4. Support stronger exam-focused review in sprint periods.
5. Prefer subtopic-level diagnosis before broad topic-level review.
6. Avoid over-updating mastery from weak evidence.
7. Avoid treating flashcard recall as identical to conceptual understanding.

---

## 3. Unified Mastery Profile Per Subject

StudyFlow should maintain exactly one mastery profile per learner per subject.

That profile is unified. It is not split into separate mastery tracks for:

- entry diagnostic quiz results
- system-suggested review quiz results
- user-created workspace quiz results

Those quiz types are only different evidence sources feeding the same profile.

### 3.1 What The Unified Profile Contains

The unified subject profile contains:

1. per-subtopic mastery states
2. per-subtopic confidence states
3. per-subtopic FSRS memory states
4. optional parent-topic aggregates derived from child subtopics
5. optional subject-level aggregates derived from all active topics

In other words:

- each subtopic has one `mastery` value
- each subtopic has one `confidence` value
- each subtopic has one `FSRS` state
- the subject view is an aggregate over these states

The system must not create separate mastery estimates just because the learner used a different quiz entry point.

### 3.2 Mastery State

`M_t in [0, 1]`

- The probability that the learner has mastered subtopic `t`.
- This is the conceptual knowledge estimate.
- Recommended source of truth: a BKT-derived latent mastery state updated in batch form.

### 3.3 Confidence State

`C_t in [0, 1]`

- The system's confidence in the current mastery estimate.
- This is not the learner's self-confidence.
- A subtopic with `M_t = 0.80` and `C_t = 0.30` should be treated very differently from one with `M_t = 0.80` and `C_t = 0.92`.

### 3.4 FSRS Memory State

For each subtopic `t`, FSRS stores:

- `S_t_fsrs`: memory stability
- `D_t_fsrs`: memory difficulty
- `R_t(d)`: retrievability on date `d`
- `due_t`: next due date implied by the card state

This is the memory model, not the mastery model.

### 3.5 Aggregate Subject Mastery

If the product needs one subject-level mastery number for dashboards, it should be derived from the unified profile rather than stored as an independent parallel truth.

A simple current-generation aggregate is:

```text
M_subject = average(M_t over active taught/current subtopics)
```

and likewise:

```text
C_subject = average(C_t over active taught/current subtopics)
```

The dashboard may show one subject mastery score, but the scheduler should still reason at the subtopic level.

---

## 4. Symbol Table

| Symbol | Meaning |
|---|---|
| `M` | mastery probability for a topic |
| `C` | confidence in the mastery estimate |
| `pT` | BKT transition probability |
| `pG` | BKT guess probability |
| `pS` | BKT slip probability |
| `pT_batch` | effective transition used once per subtopic batch |
| `R` | FSRS retrievability, probability of recall today |
| `S_fsrs` | FSRS stability |
| `D_fsrs` | FSRS difficulty |
| `n` | number of scored questions for one subtopic in one quiz batch |
| `k` | number of correct answers for one subtopic in one quiz batch |
| `n_eff` | effective batch sample size used to temper evidence strength |
| `tau` | likelihood tempering factor `n_eff / n` |
| `m_source` | mastery-update source weight |
| `u_e` | observed event performance signal for evidence group `e` |
| `n_e` | number of scored questions in objective evidence group `e` |
| `a_e` | source-strength coefficient for evidence group `e` |
| `volume_factor_e` | volume-aware strength multiplier for evidence group `e` |
| `base_strength_e` | source strength after applying volume sensitivity |
| `r_e` | recency weight for evidence group `e` |
| `w_e` | combined evidence weight for evidence group `e` |
| `alpha` | confidence-gated blend factor controlling how much mastery is allowed to move |

---

## 5. Evidence Taxonomy

Not all learner events should affect all state variables, and not all quiz types should carry the same weight.

### 5.1 The Three Quiz Types

StudyFlow has three quiz types that all feed the same mastery profile:

1. `Entry diagnostic quiz`
   Used when a learner joins mid-semester and chooses to take the initial diagnostic.

2. `System-suggested review quiz`
   Used when StudyFlow schedules or recommends an objective quiz for review, confirmation, or reinforcement.

3. `User-created workspace quiz`
   Used when the learner manually creates a quiz in the main workspace.

All three are objective evidence, but they are not equally trusted.

### 5.2 Event Types

| Event type | Updates mastery | Updates confidence | Updates FSRS |
|---|---:|---:|---:|
| Entry diagnostic quiz | Yes | Yes | Yes |
| System-suggested review quiz | Yes | Yes | Yes |
| User-created workspace quiz | Yes | Yes | Yes |
| Scored non-quiz objective review session | Yes | Yes | Yes |
| Flashcard review | No | No | Yes |
| Self-assessment | Seed only | Seed only | No |
| Preview of future content | No | No | No |

### 5.3 Relative Importance Of Quiz Types

The recommended mastery-update source weights are:

| Quiz type | `m_source` |
|---|---:|
| Entry diagnostic quiz | `1.00` |
| System-suggested review quiz | `0.90` |
| User-created workspace quiz | `0.60` |

This satisfies the product rule that:

```text
workspace quiz weight = 2/3 of system-suggested quiz weight
```

because:

```text
0.60 = 2/3 * 0.90
```

If a scored non-quiz objective review session exists, it should follow the same rules as a system-suggested review quiz unless the product later defines a distinct weight for it.

### 5.4 Why Flashcards Are Treated Differently

Flashcards are excellent evidence for memory retrieval, but weaker evidence for conceptual mastery.

A learner can remember a short prompt-answer pair and still misunderstand the wider concept.

Therefore, in the recommended algorithm:

- flashcards are first-class evidence for `FSRS`
- flashcards are not first-class evidence for `mastery`
- flashcards do not raise `confidence` in the mastery estimate by themselves

### 5.5 Why Self-Assessment Is Treated Differently

Self-assessment is useful to avoid cold start, especially in mid-semester onboarding.

However, self-assessment is subjective.

Therefore, self-assessment may initialize or seed mastery, but it should begin with lower confidence and should not, by itself, finish the diagnostic process.

---

## 6. Initialization

### 6.1 Lowest Cold Start

For a newly created subtopic with no evidence:

```text
M = 0.05
C = 0.00
awaiting_diagnostic = true
is_learned = false

pL0 = 0.05
pT  = 0.20
pG  = 0.20
pS  = 0.10
```

This is the minimum recommended cold-start mastery for the current generation.

It is intentionally low because the product requirement is that initial mastery should start at the lowest practical level.

### 6.2 If The Learner Takes The Entry Diagnostic Quiz

The learner still starts from the lowest cold start:

```text
M = 0.05
C = 0.00
awaiting_diagnostic = true
```

The difference is not the prior. The difference is the strength of the first objective evidence batch:

- diagnostic quiz has the highest mastery weight
- confidence is still low, so mastery is allowed to move faster
- the result can therefore reposition the learner quickly without requiring a high initial prior

### 6.3 If The Learner Skips The Entry Diagnostic Quiz

If the learner skips the initial diagnostic:

```text
M = 0.05
C = 0.00
awaiting_diagnostic = true
is_learned = false
```

Nothing should be promoted to diagnostic-complete simply because the learner skipped.

The scheduler should later prioritize objective confirmation on unlocked topics.

### 6.4 Optional Self-Assessment Seed

If the learner self-rates a subtopic on a `0..10` scale:

```text
M = clamp(score / 10, 0, 1)
C_store = 0.45
awaiting_diagnostic = true
is_learned = true
```

This means:

- self-assessment may seed mastery
- self-assessment may make the topic usable for planning
- self-assessment does not finish the diagnostic process

The system should still seek objective quiz evidence before treating the subtopic as well-confirmed.

---

## 7. Mastery Estimation

### 7.1 Mastery Definition

For StudyFlow, `mastery` is the posterior probability that the learner has acquired the target concept or skill represented by a subtopic.

That makes `mastery` a latent variable, not a raw score.

### 7.2 Batch-Only Mastery Updates

Mastery must be updated only once per subtopic per completed objective quiz batch.

If one completed quiz contains:

- `13` questions for subtopic A
- `10` questions for subtopic B
- `7` questions for subtopic C

then StudyFlow must perform:

- one mastery update for A
- one mastery update for B
- one mastery update for C

It must not update mastery question by question.

Question-level answers are still useful, but only as ingredients for the batch summary.

### 7.3 Batch Summary For One Subtopic

For one subtopic within one completed objective quiz:

```text
n = total scored questions for the subtopic in this quiz
k = total correct answers for the subtopic in this quiz
```

Then:

```text
batch_accuracy = k / n
```

This batch is the atomic mastery-update unit.

### 7.4 BKT Likelihood Over A Batch

Let:

- `M_old` be the current mastery probability
- `pT` be transition probability
- `pG` be guess probability
- `pS` be slip probability

For a batch of `n` questions with `k` correct:

StudyFlow should not use the raw batch likelihood directly with full `n`.

The reason is that direct binomial likelihood over `10-40` questions can produce an overly sharp Bayes factor, pushing the posterior too close to `0` or `1` after only one completed quiz.

Therefore the batch evidence must be tempered before it is allowed to move mastery.

### 7.5 Effective Sample Size And Tempering

Define:

```text
exposure_gain = 1 - exp(-n / 8)
n_eff         = 1 + 4 * exposure_gain
tau           = n_eff / n
```

Properties:

- `n_eff` grows with batch size
- `n_eff` saturates at about `5`
- long quizzes are stronger than short quizzes, but not overwhelmingly stronger
- `tau` is the likelihood tempering factor

For example, with `n = 13`:

```text
exposure_gain = 0.803
n_eff         = 4.212
tau           = 4.212 / 13 = 0.324
```

So the batch behaves like roughly `4.2` effective questions rather than `13` fully independent high-impact questions.

### 7.6 Tempered Batch Posterior

First compute the raw likelihood terms:

Likelihood if the learner was already mastered:

```text
L_mastered_raw = (1 - pS)^k * pS^(n - k)
```

Likelihood if the learner was not yet mastered:

```text
L_unmastered_raw = pG^k * (1 - pG)^(n - k)
```

Then temper them:

```text
L_mastered   = L_mastered_raw^tau
L_unmastered = L_unmastered_raw^tau
```

Batch posterior after observing the tempered batch evidence:

```text
M_obs =
    M_old * L_mastered
    -----------------------------------------
    M_old * L_mastered + (1 - M_old) * L_unmastered
```

This keeps the BKT structure but prevents a medium-sized batch from forcing mastery to an extreme posterior too quickly.

### 7.7 One Transition Per Batch

Apply one learning transition after the batch evidence:

```text
pT_batch = pT * m_source * exposure_gain
```

Then:

```text
M_candidate = M_obs + (1 - M_obs) * pT_batch
```

This means the system recognizes that a completed batch can itself be a learning event, but it does so only once per subtopic batch.

### 7.8 Confidence-Gated Mastery Movement

Mastery should not move too violently.

When confidence is low, mastery may move faster because the current estimate is uncertain.

When confidence is high, mastery should move more cautiously because the system already has a stable belief.

Define:

```text
alpha =
    clamp(
        0.10 + 0.25 * m_source * (1 - C_live) * exposure_gain,
        0.05,
        0.35
    )
```

Finally:

```text
M_new = M_old + alpha * (M_candidate - M_old)
M_new = clamp(M_new, 0.01, 0.99)
```

This formula is the main stability mechanism in the spec.

It ensures:

- low confidence -> larger allowed movement
- high confidence -> smaller allowed movement
- weak sources -> smaller movement
- large batches help, but still under damping
- even in low-confidence cases, one completed quiz cannot move mastery without limit because `alpha` is intentionally capped

### 7.9 Source Weights For Mastery Movement

Recommended `m_source` values:

| Objective source | `m_source` |
|---|---:|
| Entry diagnostic quiz | `1.00` |
| System-suggested review quiz | `0.90` |
| User-created workspace quiz | `0.60` |
| Scored non-quiz objective review session | `0.90` |
| Flashcard review | `0.00` |
| Self-assessment | `0.00` |
| Preview | `0.00` |

This keeps all quiz types inside one mastery profile while still making their influence slightly different.

### 7.10 Why This Prevents Wild Mastery Swings

The algorithm resists unstable jumps for four reasons:

1. mastery is updated once per subtopic batch, not once per question
2. raw batch evidence is tempered by `n_eff` and `tau`
3. source weight reduces weaker quiz influence
4. `alpha` shrinks automatically when confidence is already high and is capped at `0.35`

Together these rules make mastery smoother and more product-safe than naive per-question BKT accumulation.

### 7.11 Grouping Rule

Recommended grouping logic:

- `one completed quiz submission` -> split by subtopic
- `one subtopic inside one completed quiz` -> one mastery batch
- `one subtopic inside one completed quiz` -> one confidence evidence group
- `one flashcard rating` -> no mastery batch
- `one self-assessment rating` -> no mastery batch

### 7.12 Subtopic Propagation Rule

StudyFlow often schedules parent-topic tasks that are actually scoped to selected child subtopics.

The recommended rule is:

- if a task is explicitly scoped to child subtopics, the completed objective batch updates each scoped child once
- parent-level topic review eligibility is derived from children, not from forcing the parent estimate upward directly

This keeps weak subtopics visible instead of being hidden by a broad parent score.

### 7.13 Derived Study Cost

To convert mastery into approximate study effort:

```text
cost_mins = clamp(15 + round((1 - M) * 15), 10, 30)
```

Interpretation:

- weak topics cost more time
- strong topics cost less time
- the scheduler can use this as a duration estimate

### 7.14 Mastery Bands

Recommended interpretation bands:

| Mastery range | Meaning |
|---|---|
| `M < 0.30` | very weak |
| `0.30 <= M < 0.60` | progressing but unstable |
| `0.60 <= M < 0.85` | functionally good |
| `M >= 0.85` | strong mastery |

These are decision bands, not hard psychometric truths.

---

## 8. Confidence Estimation

### 8.1 Confidence Definition

`confidence` is the system's trust in the current mastery estimate.

It should increase when:

- evidence is objective
- evidence is recent
- evidence is repeated
- evidence is internally consistent
- the model's predicted correctness is close to observed correctness

It should decrease when:

- evidence is stale
- evidence is contradictory
- the only evidence is subjective self-report

Confidence is not only a display metric. It is also the control signal that reduces mastery volatility when the estimate has already become stable.

### 8.2 Evidence Window

For each topic `t`, define a recent evidence window `W_t`:

```text
W_t = all mastery-evidence groups from the last 60 days,
      capped at the 12 most recent groups
```

An evidence group means:

- one self-assessment submission for one subtopic
- one subtopic batch inside one completed entry diagnostic quiz
- one subtopic batch inside one completed system-suggested review quiz
- one subtopic batch inside one completed user-created workspace quiz
- one subtopic batch inside one scored non-quiz objective review session

Question-level events are aggregated into subtopic batches before confidence is computed.

### 8.3 Group-Level Evidence Signal

For each evidence group `e`:

```text
u_e = observed performance signal in [0, 1]
```

Recommended definition:

- self-assessment group:

```text
u_e = score / 10
```

- objective batch group:

```text
u_e = k / n
```

### 8.4 Source Strength

Each evidence group receives a source-strength coefficient `a_e`.

Recommended values:

| Evidence source | `a_e` |
|---|---:|
| Self-assessment | `0.45` |
| Scored non-quiz objective review session | `0.90` |
| System-suggested review quiz | `0.90` |
| User-created workspace quiz | `0.60` |
| Entry diagnostic quiz | `0.95` |
| Flashcard-only event | `0.00` |
| Preview-only event | `0.00` |

These values intentionally preserve the existing StudyFlow product intuition:

- self-assessment is useful but weaker
- system-suggested review quiz is the standard strong objective source
- user-created workspace quiz still counts, but only at `2/3` of the system-suggested quiz weight
- entry diagnostic quiz is slightly stronger than the normal system-suggested quiz because it initializes the learner state

### 8.5 Volume Factor

Source strength alone must not determine confidence floor.

Otherwise, even a `1-question` objective batch could incorrectly create very high confidence simply because it came from a trusted source type.

Therefore, objective evidence strength must depend on both:

- the type of source
- the amount of scored evidence in the batch

For objective evidence group `e` with `n_e` scored questions:

```text
volume_factor_e = 1 - exp(-n_e / 8)
```

For self-assessment:

```text
volume_factor_e = 1.0
```

This means:

- very short objective batches stay weak
- medium batches gain reasonable strength
- long batches saturate instead of increasing without bound

### 8.6 Base Strength

Define:

```text
base_strength_e = a_e * volume_factor_e
```

Examples for a `system-suggested review quiz` with `a_e = 0.90`:

| Questions in batch | `volume_factor_e` | `base_strength_e` |
|---|---:|---:|
| `1` | `0.1175` | `0.1058` |
| `2` | `0.2212` | `0.1991` |
| `5` | `0.4647` | `0.4183` |
| `10` | `0.7135` | `0.6421` |
| `20` | `0.9179` | `0.8261` |
| `40` | `0.9933` | `0.8939` |

This directly enforces the desired rule:

`1-question quiz should not create very high confidence`

### 8.7 Recency Weight

For each evidence group:

```text
r_e = exp(-ln(2) * age_days(e) / 45)
```

This gives confidence evidence a half-life of 45 days.

That means:

- recent evidence matters more
- old evidence still matters, but less

### 8.8 Combined Evidence Weight

```text
w_e = base_strength_e * r_e
```

This means evidence weight already reflects:

- source type
- batch size
- recency

### 8.9 Weighted Evidence Mean

```text
mu_t = sum(w_e * u_e) / sum(w_e)
```

If `sum(w_e) = 0`, use:

```text
mu_t = M_t
```

This is not the mastery value itself. It is a stability check over recent evidence.

### 8.10 Consistency Factor

Compute weighted variance over the evidence window:

```text
var_t = sum(w_e * (u_e - mu_t)^2) / sum(w_e)
```

Then:

```text
consistency_t = 1 / (1 + 4 * var_t)
```

Properties:

- if recent evidence is very consistent, `consistency_t` approaches `1`
- if recent evidence is contradictory, `consistency_t` decreases

### 8.11 Calibration Factor

For objective evidence groups only, use the model's question-level predicted correctness.

For objective group `e`:

```text
pred_e = average(predicted_p_correct for the group's question events)
err_e  = abs(pred_e - u_e)
```

Then for the topic:

```text
calibration_t =
    1 - sum(w_e * err_e) / sum(w_e)
```

This is computed only over objective evidence groups.

If no objective evidence groups exist:

```text
calibration_t = 0
```

Interpretation:

- high calibration means the learner behaved close to the model's expectations
- poor calibration means the estimated mastery is not behaving reliably in observed assessments

### 8.12 Support Factor

Let:

```text
support_t = 1 - exp(-sum(w_e) / 2.5)
```

This factor grows with more and stronger evidence, but saturates instead of growing forever.

### 8.13 Confidence Floor

Define:

```text
floor_t = max(base_strength_e over W_t)
```

This means:

- self-assessment alone gives a floor near `0.45`
- one tiny objective batch stays low
- one medium objective batch gives moderate confidence
- only a sufficiently large objective batch can create a high floor

Importantly, the floor is not allowed to jump to `0.90` from source type alone.

This avoids overconfidence from tiny quizzes while still letting long, strong, objective batches push confidence upward.

### 8.14 Stored Confidence

If there is no objective mastery evidence in the window:

```text
C_store = floor_t
```

Otherwise:

```text
C_store =
    clamp(
        floor_t
        + (1 - floor_t) * support_t * consistency_t * calibration_t,
        0.0,
        0.99
    )
```

This formula does two useful things:

1. It preserves a simple seed confidence from the strongest volume-aware evidence group.
2. It still rewards repeated, consistent, well-calibrated evidence.

The design intentionally avoids multiplying consistency and calibration into both the floor and the outer growth term, because that would double-count the same evidence quality signal.

### 8.15 Confidence Example: Tiny Quiz Versus Large Quiz

Suppose both evidence groups are:

- recent
- perfectly consistent
- perfectly calibrated
- from a `system-suggested review quiz`

Case A: `1` scored question

```text
a_e             = 0.90
volume_factor_e = 1 - exp(-1 / 8) = 0.1175
base_strength_e = 0.90 * 0.1175   = 0.1058
w_e             = 0.1058
support_t       = 1 - exp(-0.1058 / 2.5) = 0.0414
floor_t         = 0.1058

C_store =
    0.1058 + (1 - 0.1058) * 0.0414
    = 0.1428
```

So a one-question objective quiz does not create high confidence.

Case B: `20` scored questions

```text
a_e             = 0.90
volume_factor_e = 1 - exp(-20 / 8) = 0.9179
base_strength_e = 0.90 * 0.9179    = 0.8261
w_e             = 0.8261
support_t       = 1 - exp(-0.8261 / 2.5) = 0.2812
floor_t         = 0.8261

C_store =
    0.8261 + (1 - 0.8261) * 0.2812
    = 0.8750
```

So a long, strong, objective quiz can create high confidence, but only because it has both source quality and evidence volume.

### 8.16 Live Confidence Used By The Scheduler

Stored confidence should decay if nothing new happens for a long time.

Let `days_since_last_mastery_evidence = delta`.

Then the scheduler should use:

```text
C_live(today) = C_store * exp(-ln(2) * delta / 60)
```

This makes old confidence slowly weaken even if the persisted record has not been recomputed yet.

### 8.17 Confidence Bands

Recommended decision bands:

| Confidence range | Meaning |
|---|---|
| `C_live < 0.35` | low certainty |
| `0.35 <= C_live < 0.60` | moderate certainty |
| `0.60 <= C_live < 0.80` | good certainty |
| `C_live >= 0.80` | strong certainty |

---

## 9. FSRS Spaced Repetition Layer

### 9.1 Why FSRS Is Separate

Mastery and retrievability answer different questions.

- `mastery`: conceptual understanding
- `retrievability`: probability of successful recall today

High mastery does not guarantee high recall after a long gap.
High recall on a narrow card does not guarantee broad conceptual mastery.

Therefore StudyFlow should keep both.

### 9.2 FSRS State Variables

Following the FSRS model:

- `R`: retrievability, probability of recall
- `S_fsrs`: stability, defined around the interval where recall probability reaches the target retention convention
- `D_fsrs`: difficulty

The official FSRS documentation defines the memory state using `Difficulty`, `Stability`, and `Retrievability`.

### 9.3 Retrievability Formula

Using the modern FSRS formulation:

```text
R(t, S_fsrs) = (1 + factor * t / S_fsrs)^(-w20)
```

where:

```text
factor = 0.9^(-1 / w20) - 1
```

and `t` is the number of days since the last review.

This ensures:

```text
R(S_fsrs, S_fsrs) = 0.90
```

### 9.4 Interval From Target Retention

If StudyFlow wants the next review when recall probability reaches target retention `r_star`, then:

```text
I(r_star, S_fsrs) =
    S_fsrs / factor * (r_star^(-1 / w20) - 1)
```

### 9.5 Recommended Retention Targets

```text
semester target retention = 0.85
exam sprint target retention = 0.90
```

This means sprint mode can trigger earlier review pressure than normal semester mode.

### 9.6 What Events Should Update FSRS

FSRS should update on:

- entry diagnostic quiz
- system-suggested review quiz
- user-created workspace quiz
- scored non-quiz objective review session
- flashcard review

FSRS should not update on:

- self-assessment
- preview
- passive reading with no recall signal

### 9.7 Due Rule

A topic is due for memory review if either of the following is true:

```text
due_t <= today
```

or

```text
R(today) < retention_target_for_current_mode
```

In practice, `due_t` is a convenient cached scheduling boundary, while `R(today)` is the underlying memory signal.

---

## 10. Syllabus-Aware Gating

### 10.1 Continuous Semester Mode

In normal continuous learning:

- only `current` or `taught` topics may receive full practice or review tasks
- `future` topics may receive only low-pressure preview
- preview must not update mastery, confidence, or FSRS

### 10.2 Exam Sprint Mode

When an exam is close, the system may widen the scope:

- it may assign earlier full review on broader exam-relevant material
- but those tasks should be marked as exam-driven review, not standard semester flow

This preserves two product truths:

1. normal semester study should respect the class timeline
2. exam sprint may intentionally break out of that timeline

---

## 11. Two-Pass Scheduler

The scheduler should run in two passes:

1. `coverage pass`
2. `review pass`

### 11.1 Coverage Pass

Coverage pass exists to ensure taught material actually gets learned and diagnostically secured.

Coverage candidates are syllabus-unlocked topics satisfying at least one of:

```text
not is_learned
or awaiting_diagnostic = true
or (
    mastery evidence is only self-assessment
    and C_live < 0.60
)
or (
    the learner skipped the entry diagnostic
    and there is still no objective quiz batch for the topic
)
```

Coverage pass should be budget-protected. Review must not consume all available time before coverage is satisfied.

Recommended priority order inside coverage pass:

1. current lesson topics
2. taught topics still awaiting objective confirmation
3. lower confidence before higher confidence
4. lower mastery before higher mastery

Objective confirmation may be achieved by:

- entry diagnostic quiz evidence
- system-suggested review quiz evidence
- user-created workspace quiz evidence

However, weaker sources may require more repeated evidence before the topic exits the diagnostic or low-confidence regime.

### 11.2 Review Pass

Review pass uses remaining time after coverage needs are satisfied.

Review pass should choose candidates from topics that are:

- learned enough to be reviewable
- syllabus-allowed for the current mode
- weak, due, uncertain, or exam-relevant enough to justify review

---

## 12. Review Scoring In Continuous Mode

For an eligible topic, define:

```text
weakness        = 1 - M
forgetting_risk = 1 - R
uncertainty     = 1 - C_live
due_boost       = 1 if due_t <= today else 0
exam_pressure   = max(0, (30 - min(30, days_left_to_exam)) / 30)
priority_boost  = 1 if subject_is_priority else 0
```

Then compute:

```text
review_score_continuous =
    0.30 * weakness
  + 0.25 * forgetting_risk
  + 0.20 * uncertainty
  + 0.10 * due_boost
  + 0.10 * exam_pressure
  + 0.05 * priority_boost
```

Interpretation:

- weak topics should be revisited
- due or low-retrievability topics should be revisited
- uncertain topics should receive validating practice
- exam proximity should gently increase urgency

---

## 13. Review Scoring In Exam Sprint Mode

In sprint mode, retention pressure matters more.

Define:

```text
retention_gap   = max(0, retention_target_sprint - R)
weakness        = 1 - M
overdue_boost   = 1 if due_t <= today else 0
uncertainty     = 1 - C_live
exam_pressure14 = max(0, (14 - min(14, days_left_to_exam)) / 14)
priority_boost  = 1 if subject_is_priority else 0
```

Then compute:

```text
review_score_sprint =
    0.30 * weakness
  + 0.25 * retention_gap
  + 0.15 * overdue_boost
  + 0.10 * uncertainty
  + 0.10 * exam_pressure14
  + 0.10 * priority_boost
```

This emphasizes:

- weak conceptual areas
- recall risk relative to the sprint retention target
- overdue memory maintenance
- uncertainty near the exam

---

## 14. Choosing The Review Task Type

The scheduler should not only choose `which` topic to review. It should also choose `how`.

Recommended decision table:

| Condition | Preferred task type |
|---|---|
| `awaiting_diagnostic = true` | diagnostic quiz |
| `C_live < 0.35` | confirmation quiz or objective recall session |
| `M < 0.40` and `C_live >= 0.35` | targeted conceptual review, possibly followed by quiz |
| `0.40 <= M < 0.60` and `C_live < 0.60` | mixed review plus objective check |
| `0.40 <= M < 0.60` and `C_live >= 0.60` | normal review with short spacing |
| `0.60 <= M < 0.85` | standard review, can be FSRS-led |
| `M >= 0.85` and `C_live >= 0.80` | lower-frequency spaced review |
| `M >= 0.85` but `C_live < 0.80` | confirmation task before reducing review frequency |

Flashcards should be favored mainly when:

- the topic is already reasonably understood
- the main risk is forgetting, not conceptual weakness

The scheduler itself should prefer `system-suggested review quiz` when it wants objective confirmation.

`User-created workspace quiz` is still valid objective evidence, but it is user-initiated rather than scheduler-directed and therefore carries lower weight.

---

## 15. Subtopic-First Logic And Topic-Level Collapse

StudyFlow should review at subtopic level before collapsing to broad topic-level review.

### 15.1 Parent Aggregation

For a parent topic with children `i = 1..n`:

```text
M_parent = average(M_child_i)
C_parent = average(C_live_child_i)
```

Simple averaging is acceptable in the current generation.

### 15.2 When Topic-Level Review Is Allowed

A parent topic may collapse from subtopic review to topic-level review only if:

```text
all children are learned
and average child mastery >= 0.60
and average child live confidence >= 0.55
```

The `0.60` mastery threshold is a strong practical boundary for "good enough to review together".

### 15.3 When To Return To Subtopic Review

Return to subtopic-level review if any child satisfies:

```text
M_child < 0.50
or C_live_child < 0.35
```

This prevents a nice parent average from hiding a broken child concept.

---

## 16. Simulated Future State During Scheduling

When the scheduler tentatively places review tasks in a planning horizon, it should simulate a successful outcome to avoid placing duplicate review blocks too aggressively.

### 16.1 Objective Review Simulation

If the scheduled task is an objective review or quiz:

1. apply one optimistic batch-style mastery success update
2. apply one `Good` FSRS update
3. refresh due date and derived study cost

### 16.2 Flashcard-Only Simulation

If the scheduled task is flashcard-only:

1. do not change mastery
2. do not change mastery confidence
3. apply one `Good` FSRS update

This keeps the simulated horizon aligned with the semantic difference between conceptual and memory evidence.

### 16.3 Minimum Spacing

Recommended minimum spacing:

Continuous mode:

```text
2 days
```

Sprint mode:

```text
if M < 0.50: 1 day
elif M < 0.70: 2 days
else: 4 days
```

This avoids back-to-back duplicate review assignments unless the topic is genuinely weak.

---

## 17. End-To-End Update Policy

### 17.1 Entry Diagnostic Quiz Event

For one completed entry diagnostic quiz:

1. split the quiz by subtopic
2. for each subtopic batch, compute `n` and `k`
3. run one batch mastery update using:
   - `m_source = 1.00`
   - the tempered batch posterior
   - one batch transition
   - confidence-gated blending
4. create one confidence evidence group per subtopic batch
5. update FSRS using the normalized rating for that completed batch
6. if `C_store >= 0.60` after objective evidence, the subtopic may leave `awaiting_diagnostic`
7. rebuild the schedule

This is the strongest objective onboarding evidence type.

### 17.2 Skipped Entry Diagnostic

If the learner skips the entry diagnostic quiz:

```text
M remains at the lowest cold start
C remains at 0
awaiting_diagnostic remains true
```

The system may still accept self-assessment, but that does not complete diagnostic confirmation.

The scheduler should therefore prioritize later objective confirmation on available subtopics.

### 17.3 Self-Assessment Event

For one self-assessment rating:

```text
M = score / 10
C_store = 0.45
awaiting_diagnostic = true
is_learned = true
do not update FSRS
```

Then the scheduler should create or prioritize an objective confirmation task because self-assessment alone is not enough to finish the diagnostic process.

### 17.4 System-Suggested Review Quiz Event

For each subtopic inside one completed system-suggested review quiz:

1. aggregate all scored questions in the subtopic into one batch
2. compute one batch mastery update using:
   - `m_source = 0.90`
   - the tempered batch posterior
   - one batch transition
   - confidence-gated blending
3. compute `C_store` from the recent evidence window
4. update FSRS using the normalized rating
5. update `due_t`, `cost_mins`, and learned flags
6. if the subtopic now has enough objective evidence and `C_store >= 0.60`, it may exit `awaiting_diagnostic`
7. rebuild the schedule

This is the standard strong review evidence type that the scheduler itself should prefer when it needs objective confirmation.

### 17.5 User-Created Workspace Quiz Event

For each subtopic inside one completed user-created workspace quiz:

1. aggregate all scored questions in the subtopic into one batch
2. compute one batch mastery update using:
   - `m_source = 0.60`
   - the same tempered batch posterior
   - one batch transition
   - the same confidence-gated blending
3. compute `C_store` from the recent evidence window using the weaker source strength
4. update FSRS using the normalized rating
5. update `due_t`, `cost_mins`, and learned flags
6. allow this evidence to contribute to leaving `awaiting_diagnostic`, but naturally require more or better evidence because its weight is lower
7. rebuild the schedule

This is still real objective evidence. It is simply trusted less than a system-suggested review quiz.

### 17.6 Flashcard Event

For a flashcard rating:

1. update FSRS
2. recompute due date and retrievability
3. do not update mastery
4. do not update confidence

---

## 18. Worked Examples

### 18.1 Example A: Batch-Only Mastery Update For A 30-Question Quiz

A completed system-suggested review quiz contains:

- `13` questions for subtopic A
- `10` questions for subtopic B
- `7` questions for subtopic C

Suppose the learner gets:

- subtopic A: `9/13`
- subtopic B: `4/10`
- subtopic C: `6/7`

StudyFlow must perform exactly three mastery updates:

1. one batch update for subtopic A
2. one batch update for subtopic B
3. one batch update for subtopic C

It must not perform 30 independent mastery updates.

For subtopic A, assume:

```text
M_old = 0.42
C_live = 0.30
pT = 0.20
pG = 0.20
pS = 0.10
n = 13
k = 9
m_source = 0.90
```

First compute the batch likelihood terms:

```text
L_mastered_raw   = (1 - 0.10)^9 * (0.10)^4
L_unmastered_raw = (0.20)^9 * (0.80)^4
```

Then compute:

```text
exposure_gain = 1 - exp(-13 / 8) = 0.8031
n_eff         = 1 + 4 * 0.8031   = 4.2124
tau           = 4.2124 / 13      = 0.3240

L_mastered    = L_mastered_raw^tau
L_unmastered  = L_unmastered_raw^tau

M_obs =
    M_old * L_mastered
    -----------------------------------------
    M_old * L_mastered + (1 - M_old) * L_unmastered

M_obs ~= 0.7971
```

Next:

```text
pT_batch      = 0.20 * 0.90 * 0.8031 = 0.1446
M_candidate   = 0.7971 + (1 - 0.7971) * 0.1446
              = 0.8264
```

Then confidence damping limits the movement:

```text
alpha = clamp(
            0.10 + 0.25 * 0.90 * (1 - 0.30) * 0.8031,
            0.05,
            0.35
        )
      = 0.2265

M_new = 0.42 + 0.2265 * (0.8264 - 0.42)
      = 0.5121
```

Interpretation:

- the quiz length helps, but only through one saturated batch update
- the raw batch likelihood is deliberately tempered before it can dominate the posterior
- the mastery shift is moderated again by confidence
- the update happens once for A, once for B, and once for C

### 18.2 Example B: Same Performance, Different Quiz Types

Suppose the learner answers the same subtopic with the same batch result:

```text
M_old = 0.55
C_live = 0.65
n = 10
k = 7
```

If the batch comes from a system-suggested review quiz:

```text
m_source = 0.90
```

If the batch comes from a user-created workspace quiz:

```text
m_source = 0.60
```

Because the workspace quiz has only `2/3` of the system-suggested quiz weight, its:

- `pT_batch` is smaller
- `alpha` is smaller
- confidence growth is also smaller

So both events move the same unified mastery profile, but the workspace quiz moves it less aggressively.

### 18.3 Example C: Skipped Entry Diagnostic Followed By Self-Assessment

The learner joins mid-semester and skips the entry diagnostic quiz.

Initial state:

```text
M = 0.05
C = 0.00
awaiting_diagnostic = true
is_learned = false
```

Later the learner self-assesses the subtopic as `7/10`.

After self-assessment:

```text
M = 0.70
C_store = 0.45
awaiting_diagnostic = true
is_learned = true
```

Interpretation:

- the subtopic is now seeded
- the system can use it in planning
- but the diagnostic process is still incomplete
- the scheduler should still prioritize an objective confirmation quiz

### 18.4 Example D: Weak But Uncertain Topic Versus Due But Strong Topic

Compare two topics in continuous mode.

Topic A:

```text
M = 0.82
C_live = 0.88
R = 0.54
due = true
days_left_to_exam = 20
priority = false
```

Topic B:

```text
M = 0.55
C_live = 0.40
R = 0.80
due = false
days_left_to_exam = 20
priority = false
```

For Topic A:

```text
weakness        = 0.18
forgetting_risk = 0.46
uncertainty     = 0.12
due_boost       = 1
exam_pressure   = (30 - 20) / 30 = 0.33
```

So:

```text
score_A =
    0.30*0.18
  + 0.25*0.46
  + 0.20*0.12
  + 0.10*1
  + 0.10*0.33
= 0.326
```

For Topic B:

```text
weakness        = 0.45
forgetting_risk = 0.20
uncertainty     = 0.60
due_boost       = 0
exam_pressure   = 0.33
```

So:

```text
score_B =
    0.30*0.45
  + 0.25*0.20
  + 0.20*0.60
  + 0.10*0
  + 0.10*0.33
= 0.338
```

Even though Topic A is due in memory terms, Topic B is slightly more urgent because it is both weaker and far less certain. This is exactly why StudyFlow should use `mastery`, `confidence`, and `retrievability` together.

### 18.5 Example E: Subtopic Collapse To Topic Review

A chapter has three subtopics:

```text
child masteries   = [0.72, 0.64, 0.61]
child confidences = [0.77, 0.59, 0.58]
```

Then:

```text
M_parent = (0.72 + 0.64 + 0.61) / 3 = 0.6567
C_parent = (0.77 + 0.59 + 0.58) / 3 = 0.6467
```

Since:

- all children are learned
- `M_parent >= 0.60`
- `C_parent >= 0.55`

the scheduler may collapse review from child level to parent topic level.

If later one child drops to:

```text
M_child = 0.42
```

or

```text
C_live_child = 0.30
```

the scheduler should immediately return to subtopic-level review for that weak child.

---

## 19. Recommended Default Thresholds

| Parameter | Recommended value |
|---|---:|
| cold-start mastery | `0.05` |
| self-assessment confidence seed | `0.45` |
| system-suggested review quiz mastery weight | `0.90` |
| user-created workspace quiz mastery weight | `0.60` |
| entry diagnostic quiz mastery weight | `1.00` |
| system-suggested review quiz confidence strength | `0.90` |
| user-created workspace quiz confidence strength | `0.60` |
| entry diagnostic quiz confidence strength | `0.95` |
| topic-level review mastery threshold | `0.60` |
| topic-level review confidence threshold | `0.55` |
| low-confidence threshold | `0.35` |
| medium-confidence threshold | `0.60` |
| confidence recency half-life | `45 days` |
| live-confidence decay half-life | `60 days` |
| evidence window | `12 groups or 60 days` |
| semester retention target | `0.85` |
| sprint retention target | `0.90` |
| minimum continuous review spacing | `2 days` |

---

## 20. Why Not Use DKT As The Current Core

Deep Knowledge Tracing is an important research direction and often improves predictive performance on large interaction logs.

However, it is not the recommended current core for StudyFlow because:

1. it needs more event volume to shine
2. it is less transparent than BKT for product rules and debugging
3. it is harder to map cleanly into syllabus-aware scheduling rules
4. it is harder to explain to users and educators

The right current architecture is therefore:

```text
BKT mastery
+ evidence-based confidence
+ FSRS memory scheduling
+ syllabus-aware planning
```

DKT remains a future ranking or forecasting layer, not the current source of truth.

---

## 21. Future Upgrade Paths

This document recommends `C2` for now, but the next logical upgrades are clear.

### 21.1 pyBKT Upgrade Path

`pyBKT` is the natural future extension of the mastery layer because it supports:

- individualized priors and learn rates
- item-specific guess and slip parameters
- resource-specific learn rates

StudyFlow should consider moving from a single hand-tuned BKT parameter set to fitted `pyBKT` variants once the interaction logs are large enough.

### 21.2 IRT Upgrade Path

IRT is valuable if StudyFlow later wants:

- item difficulty estimation
- more rigorous test construction
- confidence intervals over ability estimates
- better adaptive assessment behavior

IRT is especially useful for quizzes and diagnostic calibration, but it is not necessary to replace the current topic-level BKT core immediately.

### 21.3 DKT Upgrade Path

DKT becomes attractive when StudyFlow has:

- long learner histories
- many repeated interactions
- richer sequential behavior patterns

At that stage, DKT can be used as a forecasting or ranking layer while BKT remains the explainable topic state for product logic.

---

## 22. Final Recommendation

If StudyFlow must choose one algorithm blueprint for the current generation, the recommended choice is:

```text
Mastery:
    BKT per subtopic, updated only by objective scored evidence
    and updated once per completed subtopic batch

Confidence:
    a separate evidence-based certainty score with
    source strength, recency, support, consistency, and calibration

Spaced repetition:
    FSRS for retrievability, due dates, and interval control

Scheduling:
    syllabus-aware coverage pass first,
    then review pass using mastery, confidence, and retrievability together
```

This is the best balance for StudyFlow right now between:

- scientific grounding
- explainability
- implementation realism
- compatibility with the current product behavior
- future extensibility

---

## References

1. FSRS algorithm wiki:
   https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm
2. FSRS legacy wiki entry pointing to the moved algorithm page:
   https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm
3. pyBKT repository and README:
   https://github.com/CAHLR/pyBKT
4. Badrinath, Wang, Pardos. "pyBKT: An Accessible Python Library of Bayesian Knowledge Tracing Models":
   https://educationaldatamining.org/EDM2021/virtual/static/pdf/EDM21_paper_269.pdf
5. Corbett and Anderson. "Knowledge tracing: Modeling the acquisition of procedural knowledge":
   https://link.springer.com/article/10.1007/BF01099821
6. Piech et al. "Deep Knowledge Tracing":
   https://papers.nips.cc/paper/5654-deep-knowledge-tracing
7. Columbia overview of Item Response Theory:
   https://www.publichealth.columbia.edu/research/population-health-methods/item-response-theory
