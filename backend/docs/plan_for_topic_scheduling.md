You are working on **StudyFlow AI**, a web-based study assistant for university students.

This project is related to **spaced repetition learning scheduling**. The backend already has a scheduler design described in:

```text
backend/SCHEDULER_DOCUMENT.md
```

First, read and reuse the scheduling ideas from that document. However, the scheduler must be adjusted to match real university learning behavior more closely.

The scheduler must become **syllabus-aware**.

Do not implement a generic spaced repetition system that freely schedules any topic from the textbook. The system must respect the real school syllabus, the actual class timeline, and the fact that students should not be fully tested on knowledge that has not yet been taught.

---

# 1. Core Scheduling Principle

StudyFlow AI has two different sources of structure:

## 1. Syllabus / Lesson Plan

The syllabus describes what the student learns in school each week or each class session.

It may contain:

```text
Week number
Class session / lesson number
Lesson title
Chapter covered
Subtopics covered
Required reading
Teaching activity
Assessment activity
Learning outcomes
```

The syllabus is the source of truth for:

```text
WHEN a topic or subtopic becomes available for practice.
```

## 2. Textbook / Learning Materials

Textbooks and uploaded materials provide the detailed learning content.

They may contain:

```text
Chapters
Sections
Subsections
Concepts
Definitions
Examples
Exercises
Past exam questions
Answer keys
```

Learning materials are the source of truth for:

```text
WHAT content is used to generate explanations, quizzes, flashcards, and citations.
```

The scheduler must combine both:

```text
Syllabus = teaching timeline
Learning materials = detailed content
Scheduler = decides when and how to practice
```

---

# 2. Topic and Subtopic Hierarchy

Currently, a `topic` is equivalent to a chapter in the textbook.

However, this is too broad for realistic scheduling.

A topic can span multiple school sessions. Therefore, each topic must contain multiple `subtopics`.

Example:

```text
Topic: Chapter 1 — Introduction to Philosophy

Subtopic 1:
- Concept of philosophy
- Taught in Week 1 / Lesson 1

Subtopic 2:
- The basic question of philosophy
- Taught in Week 1 / Lesson 2

Subtopic 3:
- Worldview and methodology functions
- Taught in Week 2 / Lesson 3
```

In this example, the scheduler must not include Subtopic 3 in a normal quiz, flashcard session, review task, mastery check, or mock test before Week 2 / Lesson 3 has happened.

The real scheduling unit should be the `subtopic`, not the parent `topic`.

A topic is a parent grouping unit. A subtopic is the actual unit that becomes available after a specific class session.

---

# 3. Critical Rule: Never Practice Untaught Subtopics

The most important rule is:

```text
StudyFlow must never schedule full practice, review, quiz, flashcards, mastery evaluation, or mock-test tasks for a subtopic before that subtopic has been taught in school.
```

In continuous semester learning mode:

```text
A subtopic is locked until its syllabus lesson has been completed.
```

Only after the corresponding school lesson has happened can StudyFlow schedule:

```text
Quiz
Flashcards
Review task
Mastery check
Spaced repetition
AI explanation task
Weak-subtopic reinforcement
```

Before that class session happens, the system may only allow optional **light preview**.

Light preview is not normal practice.

Light preview may include:

```text
Short overview
Key terms
Guiding questions
Simple AI explanation
Reading reminder
```

Light preview must not strongly update mastery and must not count as normal learning progress.

---

# 4. Important Clarification: Partial Topic Review Is Allowed

StudyFlow is still allowed to schedule review, quizzes, flashcards, and practice tasks for a topic even if the whole topic has not been fully completed in school yet.

However, in that case, the task must only use the subtopics that have already been taught.

The scheduler must not touch, test, review, or evaluate any subtopic that has not been taught yet.

This means a topic can be **partially available**.

Example:

```text
Topic: Chapter 1

Subtopic 1:
- Taught in Lesson 1
- Status: taught
- Eligible for quiz, flashcard, review, mastery evaluation

Subtopic 2:
- Taught in Lesson 2
- Status: taught
- Eligible for quiz, flashcard, review, mastery evaluation

Subtopic 3:
- Taught in Lesson 3
- Status: not taught yet
- Locked for normal practice
```

In this situation, StudyFlow may create tasks such as:

```text
Review Chapter 1 — only taught parts
Quiz: Chapter 1 learned subtopics
Flashcards: Chapter 1 taught subtopics
Review: Subtopic 1 and Subtopic 2
```

But StudyFlow must not create tasks such as:

```text
Full Chapter 1 quiz
Full Chapter 1 mock test
Full Chapter 1 mastery evaluation
Flashcards including Subtopic 3
Any task that includes Subtopic 3
```

because Subtopic 3 has not been taught yet.

---

# 5. Whole-Topic Practice Rule

A topic becomes fully available only when all of its subtopics have been taught in school.

Before all subtopics are taught:

```text
Allowed:
- Practice taught subtopics inside the topic
- Review taught subtopics
- Quiz taught subtopics
- Flashcards for taught subtopics
- Partial topic progress calculation
- Partial topic review label

Not allowed:
- Full-topic quiz
- Full-topic mock test
- Full-topic mastery evaluation
- Practice that includes untaught subtopics
```

After all subtopics in the topic have been taught:

```text
Allowed:
- Full-topic quiz
- Full-topic review
- Full-topic mastery evaluation
- Mixed practice across all subtopics in the topic
- Topic-level mock test section
```

---

# 6. Topic Completion State

Each topic should have a completion state based on its subtopics.

```text
not_started:
  No subtopic has been taught yet.

partially_taught:
  Some subtopics have been taught, but at least one subtopic is still locked.

fully_taught:
  All subtopics in the topic have been taught in school.
```

The scheduler should behave differently for each state.

## not_started

The scheduler must not create normal learning tasks for this topic.

Only optional light preview is allowed if this topic or one of its subtopics belongs to the next lesson.

## partially_taught

The scheduler may create review and practice tasks, but only for taught subtopics.

The UI should clearly label these tasks as partial-topic tasks.

Examples:

```text
Quiz: Chapter 1 learned parts
Review: Chapter 1 Subtopics 1–2
Flashcards: Taught subtopics in Chapter 1
```

## fully_taught

The scheduler may create full-topic tasks.

Examples:

```text
Full Chapter 1 review
Chapter 1 mastery check
Mixed quiz for Chapter 1
Mock test section for Chapter 1
```

---

# 7. Subtopic Availability Status

Each subtopic should have a teaching availability status.

Conceptually:

```text
locked
preview_available
current
taught
review_due
mastered
```

## locked

The subtopic belongs to a future school session.

The scheduler must not create normal practice tasks for it.

## preview_available

The subtopic belongs to the next upcoming school lesson.

Only light preview is allowed.

## current

The subtopic belongs to the latest or current school session.

The scheduler should prioritize practice soon after class.

## taught

The subtopic has already been taught.

It is eligible for spaced repetition and mastery evaluation.

## review_due

The subtopic has been taught and is due for spaced repetition.

## mastered

The student has shown strong performance on this subtopic.

It can be scheduled less frequently.

---

# 8. Scheduling Candidate Filtering

Before generating any schedule, the system should classify subtopics.

Conceptually:

```text
lockedSubtopics = subtopics where the school lesson has not happened yet
currentSubtopics = subtopics from the latest school lesson
taughtSubtopics = subtopics from completed lessons
previewSubtopics = subtopics from the next lesson only
```

Then:

```text
normalSchedulingCandidates = currentSubtopics + taughtSubtopics
previewCandidates = nextLessonSubtopics
blockedCandidates = lockedSubtopics excluding previewCandidates
```

The scheduler must never schedule `blockedCandidates` as normal learning tasks.

For partially taught topics, normal scheduling can use only the taught subtopics within that topic.

---

# 9. Continuous Semester Learning Mode

Continuous semester mode should be syllabus-aware.

Before the final exam window, it should prioritize:

```text
1. Subtopics from the latest school lesson
2. Taught subtopics that are due for spaced repetition
3. Taught subtopics with low mastery
4. Partial-topic review using only taught subtopics
5. Optional light preview for the next lesson
```

It must not prioritize:

```text
1. Future locked subtopics
2. Full-topic practice for topics that are only partially taught
3. Mock tests covering content not yet taught
4. Random textbook sections that are not yet in the syllabus timeline
```

The product behavior should feel like this:

```text
The student just learned something in class.
StudyFlow helps them practice it as soon as possible.
```

After a school lesson is completed, StudyFlow should generate short practice tasks for the subtopics taught in that lesson.

Examples:

```text
After Week 1 / Lesson 1:
- 10-minute quiz for Subtopic 1
- 8 flashcards for Subtopic 1
- Optional AI explanation task
```

These tasks should be scheduled soon after the class session, preferably on the same day or the next available study slot.

---

# 10. Spaced Repetition Behavior

Reuse the spaced repetition scheduling logic from `SCHEDULER_DOCUMENT.md`, but apply it only to eligible subtopics.

A subtopic becomes eligible for spaced repetition only after it has been taught.

The scheduler should consider:

```text
Last review time
Review interval
Mastery score
Quiz accuracy
Flashcard rating
Difficulty
Due date
Exam date
Available study time
Course priority
```

However, the scheduler must always filter out locked subtopics first.

The scheduling flow should conceptually be:

```text
1. Load syllabus timeline.
2. Determine current school week / lesson.
3. Mark subtopics as locked, preview_available, current, taught, review_due, or mastered.
4. Remove locked subtopics from normal scheduling candidates.
5. Generate immediate practice for current lesson subtopics.
6. Generate spaced repetition tasks for taught subtopics.
7. Generate weak-subtopic reinforcement for taught weak subtopics.
8. Allow partial-topic review only over taught subtopics.
9. Optionally generate light preview for the next lesson.
10. When exam is near, switch to exam sprint behavior.
```

---

# 11. Task Types and Eligibility

## Quiz Task

Allowed for:

```text
Current subtopics
Taught subtopics
Taught subtopics inside partially taught topics
Exam sprint scope
```

Not allowed for locked future subtopics in continuous mode.

## Flashcard Task

Allowed for:

```text
Current subtopics
Taught subtopics
Taught subtopics inside partially taught topics
Exam sprint scope
```

Not allowed for locked future subtopics in continuous mode.

## Review Task

Allowed only for taught subtopics.

For a partially taught topic, review can cover only taught subtopics.

## Mastery Evaluation

Allowed only for taught subtopics.

Full-topic mastery evaluation is allowed only when the topic is fully taught.

## Mock Test

In continuous mode:

```text
May cover only taught subtopics.
```

In exam sprint mode:

```text
May cover full exam scope.
```

## Preview Task

Allowed only for the next lesson.

It should be low-pressure and should not strongly affect mastery.

---

# 12. Topic and Subtopic Mastery

Mastery must be evaluated at two levels:

```text
Topic mastery
Subtopic mastery
```

A topic is a parent unit, usually a textbook chapter.

A subtopic is a smaller unit taught in a specific school session.

Each subtopic must have its own mastery progress.

The topic progress bar should be calculated from the mastery of its subtopics.

Example:

```text
Topic A has 3 subtopics.

Subtopic A1 mastery = 100%
Subtopic A2 mastery = 0%
Subtopic A3 mastery = 0%

Topic A mastery = 33%
```

If a topic has 3 subtopics, then each subtopic contributes about 33.33% to the topic mastery.

General rule:

```text
Topic mastery = average mastery of all subtopics inside that topic
```

or:

```text
Topic mastery = sum(subtopic mastery × subtopic weight)
```

For MVP, equal weights are acceptable.

If the topic has 4 subtopics, each subtopic contributes 25%.

If the topic has 5 subtopics, each contributes 20%.

---

# 13. Overall Mastery vs Available Mastery

The UI should distinguish between two meanings if needed.

## Overall Topic Mastery

This reflects progress across the entire topic/chapter.

Future locked subtopics still belong to the topic, so the topic may not reach 100% until all subtopics are taught and mastered.

Example:

```text
Topic has 3 subtopics.
Only 1 has been taught and mastered.

Overall topic mastery = 33%
```

## Available Mastery

This reflects mastery only among subtopics that have already been taught.

This is useful so the student does not feel punished for future content.

Example:

```text
Topic has 3 subtopics.
Only Subtopic 1 has been taught.
Subtopic 1 mastery = 100%.

Available mastery = 100% of taught content.
Overall topic mastery = 33% of entire topic.
```

For scheduling decisions, use taught/available subtopics.

For full topic progress, use all subtopics.

---

# 14. Progress Bars

The UI should support progress bars at both levels.

## Topic Progress Bar

Shows overall progress of the chapter/topic.

Example:

```text
Chapter 1 — 33%
```

This can be calculated from all subtopics.

## Subtopic Progress Bar

Shows mastery for a specific subtopic.

Example:

```text
Concept of philosophy — 80%
Basic question of philosophy — 45%
Worldview function — Locked until Week 2 / Lesson 3
```

Locked subtopics should be visibly marked as locked or upcoming, not treated as failed.

For a partially taught topic, the UI should clearly show:

```text
Topic: Chapter 1
Overall mastery: 60%
Available mastery: 90%
Status: partially taught
```

---

# 15. Exam Sprint Transition

Continuous semester learning should continue until the exam is near.

When the exam is 14 days away or less, the system should switch to exam sprint behavior.

Rule:

```text
If course mode = continuous
and days until exam > 14:
    use syllabus-aware continuous scheduling

If course mode = continuous
and days until exam <= 14:
    switch to exam sprint scheduling

If course mode = exam_sprint:
    use exam sprint scheduling immediately
```

In exam sprint mode, the system may use the full exam scope, including topics and subtopics from the whole course, depending on the syllabus and exam coverage.

Exam sprint should prioritize:

```text
Weak subtopics
Weak topics
Important topics
Past exam patterns
Mock tests
Mixed-topic quizzes
Flashcards due for review
Previously wrong questions
```

---

# 16. Mid-Semester User Flow

Many students start using StudyFlow in the middle of a semester.

Example:

```text
The student creates a course in Week 4.
The syllabus shows that Weeks 1, 2, and 3 have already been taught.
```

In this case, the system should not assume the student is starting from zero.

Instead, it should:

```text
1. Ask the student which week or lesson they are currently at.
2. Use the syllabus to identify all subtopics already taught.
3. Generate a diagnostic test only for taught subtopics.
4. Estimate mastery for each taught subtopic.
5. Aggregate subtopic mastery into topic mastery.
6. Generate a catch-up and review plan.
7. Continue following the syllabus from the current point onward.
```

The diagnostic test must not include locked future subtopics.

---

# 17. Diagnostic Test

The diagnostic test should evaluate previously taught subtopics.

Its purpose is not grading.

Its purpose is to initialize the student's mastery profile.

The result should be calculated at subtopic level first.

Example:

```text
Subtopic A1: 80%
Subtopic A2: 40%
Subtopic A3: 60%
```

Then topic mastery is calculated from subtopic mastery.

Example:

```text
Topic A has 3 subtopics.

A1 = 80%
A2 = 40%
A3 = 60%

Topic A mastery = (80 + 40 + 60) / 3 = 60%
```

The scheduler should then use weak subtopics to create catch-up tasks.

---

# 18. Catch-Up Scheduling

If a student starts mid-semester, the scheduler should avoid overwhelming them.

It should not schedule all previous content immediately.

Instead, it should create a realistic catch-up plan:

```text
Today:
- Practice latest lesson subtopics

Tomorrow:
- Review one weak subtopic from a previous lesson

Later this week:
- Flashcards for another weak taught subtopic

Next class:
- Continue with the syllabus timeline
```

Catch-up tasks must still respect available study time.

Catch-up tasks must only use taught subtopics.

---

# 19. Scheduler Output Requirements

When the scheduler creates a task, each task should explain why it exists.

Each scheduled task should be linked to:

```text
Course
Topic
Subtopic
Syllabus lesson
Task type
Reason
Earliest allowed time
Due time if applicable
Whether this is a partial-topic task or full-topic task
```

Example task for recently taught subtopic:

```text
Quiz: Concept of philosophy

Reason:
This subtopic was taught in Week 1 / Lesson 1 and should be practiced soon after class.

Linked syllabus lesson:
Week 1 / Lesson 1

Linked topic:
Chapter 1

Linked subtopic:
Concept of philosophy
```

Example partial-topic task:

```text
Quiz: Chapter 1 learned parts

Reason:
Chapter 1 is partially taught. This quiz only includes subtopics already taught in school.

Included subtopics:
- Subtopic 1
- Subtopic 2

Excluded subtopics:
- Subtopic 3, because it has not been taught yet.
```

Example full-topic task:

```text
Full Chapter 1 Review

Reason:
All subtopics in Chapter 1 have now been taught. Full-topic review is unlocked.
```

Example preview task:

```text
Preview: Worldview function

Reason:
This subtopic belongs to the next school lesson. This is only a light preview.
```

---

# 20. Required Product Behavior Summary

The scheduler must behave as follows:

```text
1. Read the scheduling logic from SCHEDULER_DOCUMENT.md.
2. Keep the spaced repetition principle.
3. Add syllabus-aware constraints.
4. Treat topic as a parent unit.
5. Treat subtopic as the real scheduling unit.
6. Do not schedule untaught subtopics for normal practice.
7. Allow partial-topic practice only over taught subtopics.
8. Unlock full-topic practice only when all subtopics in the topic have been taught.
9. Generate practice soon after a subtopic is taught.
10. Evaluate mastery at subtopic level.
11. Aggregate subtopic mastery into topic mastery.
12. Show progress bars for both topic and subtopic.
13. Distinguish overall topic mastery from available mastery if needed.
14. Use diagnostic tests for mid-semester users.
15. Use only taught subtopics in diagnostic tests.
16. Switch to exam sprint behavior when the exam is within 14 days.
17. In exam sprint mode, allow broader exam-scope review.
18. Do not hardcode any example syllabus, course, textbook, topic, or university.
```

---

# 21. Acceptance Criteria

The implementation is correct if:

```text
- A future subtopic is never scheduled for normal quiz, flashcard, review, or mastery evaluation before its syllabus lesson.
- A topic can span multiple school lessons.
- A subtopic belongs to exactly one school lesson for scheduling purposes.
- Practice for a subtopic can begin only after the relevant class session.
- A partially taught topic can still be reviewed, but only through its taught subtopics.
- Full-topic practice is unlocked only after every subtopic inside the topic has been taught.
- The scheduler prioritizes recently taught subtopics in continuous mode.
- The scheduler uses spaced repetition only for taught subtopics.
- Topic mastery is calculated from subtopic mastery.
- If a topic has 3 equal subtopics, one fully mastered subtopic contributes about 33% to the topic.
- The UI can show progress at both topic and subtopic level.
- Locked subtopics are shown as locked/upcoming, not as failed.
- Mid-semester users receive a diagnostic test based only on already taught subtopics.
- Exam sprint mode starts when the exam is within 14 days.
- The system remains generic and does not hardcode the example course or syllabus.
```
