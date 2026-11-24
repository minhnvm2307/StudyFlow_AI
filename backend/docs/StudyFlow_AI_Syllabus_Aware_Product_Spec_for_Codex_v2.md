# StudyFlow AI — Syllabus-Aware Learning Product Specification for Codex

> This document explains the intended product behavior of StudyFlow AI after adding syllabus-aware learning.  
> It is written for Codex to understand the product logic before implementation.  
> This is **not** a low-level code specification.  
> Do **not** hardcode the examples. They are included only to clarify the intended behavior.

---

## 1. Product Context

StudyFlow AI is a web-based study assistant for university students.

The product helps students:

- Create a course workspace.
- Add learning materials such as textbooks, slides, notes, past exams, and answer keys.
- Ask questions through an AI chatbot.
- Generate quizzes and flashcards.
- Track topic mastery.
- Schedule study tasks.
- Prepare for exams.

The important product change described in this document is:

**StudyFlow AI should not treat a course as a flat collection of uploaded documents. It should understand how the course is actually taught over time.**

In real university courses, students usually learn according to a syllabus or lesson plan. They do not learn all chapters at once. They learn week by week, lecture by lecture, seminar by seminar.

Therefore, StudyFlow AI should become **syllabus-aware**.

---

## 2. The Main Problem

The current simple approach is:

```text
Create course
→ Upload documents
→ Extract topics from documents
→ Generate quizzes, flashcards, and schedule
```

This is not realistic enough.

A textbook may contain the entire course, but the student may only have learned the first few lessons. If StudyFlow immediately generates tasks from future chapters, it may ask the student to practice knowledge that has not been taught yet.

This creates several problems:

1. The study plan does not match the real class schedule.
2. The student may feel overwhelmed.
3. The system may generate quizzes for topics the student is not expected to know yet.
4. Continuous semester learning becomes unrealistic.
5. The system cannot properly handle students who start using the app in the middle of a semester.

The solution is to introduce a syllabus-aware layer.

---

## 3. Core Product Principle

The key principle is:

**The syllabus defines the real teaching timeline.  
The learning materials define the detailed knowledge content.**

In other words:

- The syllabus tells StudyFlow **when** a topic is taught.
- The textbook and uploaded materials tell StudyFlow **what** the content means.
- The mapping between them tells StudyFlow **which material sections support each class lesson**.

This means StudyFlow should not simply extract topics from a textbook and schedule them freely.

Instead, StudyFlow should first understand the syllabus, then map learning materials to that syllabus, then generate learning activities based on what has already been taught or is currently being taught.

---

## 4. Important Distinction: Syllabus vs Learning Materials

Codex should clearly understand that these are different objects with different purposes.

### 4.1 Syllabus

A syllabus is the course delivery plan.

It may describe:

- Course weeks.
- Lesson numbers.
- Lecture topics.
- Seminar topics.
- Reading assignments.
- Required chapters or sections.
- Teaching activities.
- Assessment activities.
- Learning outcomes.
- Exam milestones.

The syllabus answers questions like:

- What is taught in Week 1?
- What is taught in Lesson 3?
- Which textbook sections are assigned for this lecture?
- What should the student have already learned by now?
- What is coming next?
- When should the student switch to exam preparation?

### 4.2 Learning Materials

Learning materials provide the actual content used for studying.

They may include:

- Textbooks.
- PDF chapters.
- Slides.
- Lecture notes.
- Past exams.
- Answer keys.
- Student notes.
- Web pages.
- Handouts.

Learning materials answer questions like:

- What is the definition of this concept?
- What explanation should the chatbot use?
- What source should be cited?
- What content should be used to generate quiz questions?
- What content should be used to create flashcards?

### 4.3 Why This Distinction Matters

A textbook often has a hierarchical content structure such as:

```text
Part
→ Chapter
→ Section
→ Subsection
→ Micro-topic
```

A syllabus often has a teaching timeline structure such as:

```text
Week
→ Lesson
→ Lecture or seminar
→ Assigned readings
→ Activities
→ Assessment
```

These two structures are not the same.

StudyFlow must connect them through a mapping process.

---

## 5. Generic Examples Only — Do Not Hardcode

The examples below are only for understanding.

For example, a syllabus may say:

```text
Week 1 / Lesson 1:
Introduction to philosophy and the basic concept of philosophy.
Required reading: Chapter 1, Section I.
```

A textbook may contain:

```text
Part I
Chapter I
I. What is philosophy?
1. Philosophy and its object
a) The concept of philosophy
2. The basic question of philosophy
```

StudyFlow should understand that the syllabus lesson corresponds to some textbook sections.

However, Codex must not hardcode:

- A specific university.
- A specific course code.
- A specific syllabus URL.
- A specific Marxist philosophy structure.
- Specific chapter names.
- Specific Vietnamese headings.

The system should be generic and work for many courses and many syllabus formats.

The product behavior should support any course where there is:

- A timeline of lessons.
- A set of learning materials.
- A need to map lesson topics to material sections.

---

## 6. Three Core Structures

StudyFlow should reason about three separate but connected structures.

### 6.1 Course Delivery Structure

This comes from the syllabus.

Examples of delivery units:

- Week 1.
- Week 2.
- Lesson 1.
- Lecture 3.
- Seminar 2.
- Lab 4.
- Midterm review.
- Final exam review.

A delivery unit represents what the student experiences in the real course schedule.

### 6.2 Knowledge Content Structure

This comes from textbooks and learning materials.

Examples of content units:

- Part.
- Chapter.
- Section.
- Subsection.
- Concept.
- Definition.
- Theory.
- Example.
- Exercise.
- Past exam question.

A content unit represents what the student can study, ask about, practice, or cite.

### 6.3 Mapping Structure

This connects the syllabus to the materials.

A mapping answers:

```text
This syllabus lesson is supported by these textbook sections, slides, notes, and past exam questions.
```

Example:

```text
Lesson 3 covers:
- Textbook Chapter 1, Section II
- Slide Week 3
- Past exam questions tagged with the same concept
```

This mapping is the bridge between real classroom progress and AI-generated study activities.

---

## 7. Syllabus-Aware Topic Map

The topic map should not be generated only from uploaded documents.

The topic map should be created using both:

1. The syllabus timeline.
2. The content hierarchy from materials.

The syllabus should define the main course structure and learning order.

The materials should provide detailed subtopics, explanations, and citations.

A good topic map should include:

- Which lesson introduces the topic.
- Which materials explain the topic.
- Whether the topic has already been taught.
- Whether the topic is currently being learned.
- Whether the topic is only for future lessons.
- How important the topic is.
- Whether the topic is suitable for quiz, flashcards, chatbot explanation, or mock test.

This allows StudyFlow to schedule learning tasks more realistically.

---

## 8. Topic Granularity

Syllabi vary in detail. Some are broad and chapter-based. Others are detailed and list sections or subtopics.

StudyFlow should support multiple levels of topic granularity.

### 8.1 Chapter-Level Topics

Some syllabi only mention chapters.

Example:

```text
Week 1: Chapter 1
Week 2: Chapter 2
Week 3: Chapter 3
```

This is broad but still useful for scheduling.

### 8.2 Section-Level Topics

Some syllabi mention specific sections.

Example:

```text
Week 1: Chapter 1, Sections 1.1 and 1.2
Week 2: Chapter 1, Sections 1.3 and 1.4
```

This is better for practice generation.

### 8.3 Micro-Topics

Micro-topics are often extracted from learning materials.

Example:

```text
Concept A
Concept B
Definition C
Theory D
Method E
```

These are useful for flashcards, quizzes, and diagnostic tests.

### 8.4 Recommended Behavior

StudyFlow should not force every course into one fixed granularity.

Instead:

- If the syllabus is broad, use chapters as lesson-level topics and extract micro-topics from materials.
- If the syllabus is detailed, use sections or subtopics directly.
- If materials are detailed but the syllabus is broad, keep the syllabus as the timeline and attach detailed material-derived topics under each lesson.
- If the syllabus and materials disagree, prefer the syllabus for teaching order and the materials for content detail.

---

## 9. Continuous Semester Learning Mode

Continuous semester learning is the mode for students who are learning a course across the semester.

In this mode, the main goal is:

**Help the student practice recently taught knowledge as soon as possible, while keeping review tasks aligned with the real class timeline.**

This mode should feel like a companion that follows the student's university class.

It should not feel like a generic exam cram tool.

### 9.1 What Continuous Mode Should Prioritize

Continuous mode should prioritize:

1. The most recently taught lesson.
2. Topics taught in the last class.
3. Topics taught in previous weeks that are due for review.
4. Weak topics from previous lessons.
5. Light preview for the next lesson, only when appropriate.

### 9.2 What Continuous Mode Should Avoid

Continuous mode should avoid:

1. Deep practice for future lessons.
2. Full quizzes on untaught topics.
3. Flashcard sets from chapters not yet taught.
4. Mock tests covering the whole course too early.
5. Random topic selection from the entire textbook.

### 9.3 Main User Expectation

A student using continuous mode usually wants:

```text
I just learned something in class.
Help me practice it soon so I do not forget it.
```

This is the central experience of continuous learning.

---

## 10. The Untaught Topic Rule

This is one of the most important rules.

In continuous semester learning mode:

**StudyFlow must not assign full learning tasks for topics that have not been taught yet.**

A full learning task includes:

- Full quiz.
- Flashcard practice set.
- Mock test section.
- Mastery evaluation.
- Required review task.

Allowed topics are:

- Topics from completed lessons.
- Topics from the current lesson.
- Previously taught topics that need review.

A future topic may only be used for light preview.

### 10.1 Light Preview Exception

Light preview means low-pressure exposure to upcoming content.

Examples:

- Read a short summary.
- View key terms.
- Ask AI for a simple overview.
- See guiding questions before the next class.

Light preview should not be treated as mastery practice.

The system should not score the student heavily on preview content.

---

## 11. Active Learning Mode

StudyFlow should distinguish between the user's selected course mode and the system's active learning behavior.

A course may be created with one of these base modes:

- Continuous semester learning.
- Exam sprint learning.

However, a continuous course should automatically enter exam sprint behavior when the exam is near.

### 11.1 Continuous Mode Before the Exam Window

If the student selected continuous semester learning and the exam is more than 14 days away:

```text
Active behavior = syllabus-aware continuous learning
```

The system follows the syllabus and avoids untaught topics.

### 11.2 Continuous Mode Near the Exam

If the student selected continuous semester learning and the exam is 14 days away or less:

```text
Active behavior = exam sprint
```

The system should notify the student and shift the schedule toward exam preparation.

### 11.3 Exam Sprint Selected From the Beginning

If the student selected exam sprint mode from the beginning:

```text
Active behavior = exam sprint immediately
```

This is useful when the student joins near the exam or only wants short-term exam preparation.

---

## 12. Exam Sprint Mode

Exam sprint mode is different from continuous semester learning.

In exam sprint mode, the system assumes the student is preparing for an exam and needs high-impact review.

The system can use the full exam scope, not only the recently taught lesson.

Exam sprint mode should prioritize:

- Weak topics.
- Important topics.
- Frequently tested topics.
- Past exam questions.
- Mixed-topic quizzes.
- Mock tests.
- Flashcards due for review.
- Mistakes from previous quizzes.
- Final checklist.

In this mode, it is acceptable to assign full-course review tasks if they are within the exam scope.

The schedule can become more intense than continuous mode.

---

## 13. Student Starts Mid-Semester

Many users will not start using StudyFlow from Week 1.

A common case:

```text
The course is already in Week 4.
The student has learned Weeks 1, 2, and 3 in class.
The student creates the course in StudyFlow for the first time.
```

StudyFlow should not assume that the student is completely new.

Instead, StudyFlow should ask:

- Which week are you currently in?
- What was the most recent lesson taught?
- Which class sessions have already happened?
- Do you want to take a short diagnostic test?

The syllabus is necessary here because it tells the system which topics should already have been taught by the current point in the semester.

---

## 14. Diagnostic Test for Mid-Semester Users

When a student starts mid-semester, StudyFlow should offer a diagnostic test.

The diagnostic test is not a formal exam.

Its purpose is to estimate the student's mastery of topics that were already taught before they started using the system.

### 14.1 What the Diagnostic Test Should Cover

The test should cover only topics that have already been taught according to the syllabus.

If the student is at Week 4, the test may cover:

- Week 1 topics.
- Week 2 topics.
- Week 3 topics.
- The current Week 4 topic only if it has already been taught.

It should not test future topics.

### 14.2 What the Diagnostic Test Should Produce

The result should not only be a total score.

It should estimate mastery by topic.

Example output:

```text
Topic A: strong
Topic B: weak
Topic C: uncertain
Topic D: needs review
```

The system should then use this to generate a catch-up plan.

### 14.3 How the Diagnostic Test Should Feel

The diagnostic test should feel short and helpful.

It should not feel like a stressful exam.

The tone should be:

```text
Let us quickly check what you already know so StudyFlow can personalize your plan.
```

---

## 15. Catch-Up Plan for Mid-Semester Users

After the diagnostic test, StudyFlow should create a catch-up plan.

The catch-up plan should:

- Review weak topics from previous lessons.
- Practice the most recent lesson.
- Keep the student aligned with the current class.
- Avoid overwhelming the student with all missed content at once.
- Still follow the future syllabus timeline.

Example:

```text
Today:
- Practice the most recent lesson.

Tomorrow:
- Review one weak topic from Week 2.

Later this week:
- Do flashcards for Week 1 terms.

Next class:
- Continue following the syllabus.
```

This is better than simply telling the student to restart from Week 1.

---

## 16. How StudyFlow Should Generate the Learning Plan

StudyFlow should generate the learning plan differently depending on the active behavior.

### 16.1 Continuous Semester Learning Plan

The plan should be based on:

- The syllabus.
- The current week or lesson.
- Recently taught topics.
- Previously taught weak topics.
- Spaced repetition needs.
- The student's available study time.

The plan should include:

- Practice after class.
- Short quizzes.
- Flashcards.
- Review tasks.
- Optional preview tasks.
- AI explanation tasks.

It should not include:

- Full future topic practice.
- Full-course mock tests too early.
- Random advanced topics from future chapters.

### 16.2 Exam Sprint Learning Plan

The plan should be based on:

- Days until exam.
- Target score.
- Topic mastery.
- Topic importance.
- Past exam patterns.
- Available study time.
- Remaining syllabus scope.

The plan should include:

- Mixed-topic quizzes.
- Weak-topic review.
- Mock tests.
- Flashcards due for review.
- Past exam practice.
- Final checklist.
- AI explanation for mistakes.

---

## 17. How Uploaded Materials Should Be Used

Uploaded materials should not override the syllabus timeline.

Instead, they should support the syllabus.

For each syllabus lesson, StudyFlow should try to find relevant content from the uploaded materials.

For example:

```text
Lesson: Week 2, Lecture 2
Syllabus topic: Basic problem of philosophy
Mapped materials:
- Textbook Chapter 1, Section II
- Slide week_02.pdf
- Student notes from class
- Past exam questions about this topic
```

The chatbot should use mapped materials when answering questions about that lesson.

Quiz and flashcard generation should also prefer mapped materials.

If no material is mapped to a syllabus lesson, the system may still create a placeholder lesson structure, but should warn the user that more materials are needed for high-quality AI output.

---

## 18. What Happens If There Is No Syllabus

Syllabus-aware behavior is ideal, but the system should still work if the user does not have a syllabus.

If no syllabus is available, StudyFlow can fall back to material-based topic extraction.

However, the product should clearly communicate that the plan may be less aligned with the real class schedule.

Fallback behavior:

- Extract chapters and topics from uploaded materials.
- Ask the user to choose which chapter or topic they are currently learning.
- Use that answer as a simplified syllabus position.
- Allow the user to manually mark topics as taught or not taught.

This prevents the system from becoming unusable without a formal syllabus.

---

## 19. User Interface Implications

This document is mainly about behavior, but Codex should understand the UI implications.

### 19.1 Course Creation / Onboarding

The course creation flow should include a syllabus step or syllabus section.

The user should be able to:

- Upload a syllabus.
- Use a system syllabus template.
- Manually create a simple lesson plan.
- Skip syllabus setup temporarily.

The system should also ask:

- What week are you currently in?
- What was the most recent lesson?
- Are you starting from the beginning or joining mid-semester?

### 19.2 Dashboard

The dashboard should show the relationship between tasks and the real class timeline.

Examples:

- Latest class lesson.
- Current syllabus week.
- Practice task for the most recent lesson.
- Catch-up task from a weak previous topic.
- Exam sprint transition notice when the exam is near.

### 19.3 Course Page

Course cards may show syllabus progress.

Examples:

```text
Week 3 of 15
Latest lesson: Lesson 6
Exam sprint starts in 5 days
```

### 19.4 Study Workspace

The workspace should include a way to view syllabus progress.

This can be a panel, tab, or section showing:

- Completed lessons.
- Current lesson.
- Upcoming lessons.
- Topics inside each lesson.
- Related materials.
- Practice actions for each lesson.

### 19.5 Schedule Page

Calendar events should explain why they exist.

Examples:

```text
Quiz: Topic A
Based on Week 3, Lesson 6

Review: Topic B
Weak topic from Week 2

Preview: Topic C
Next lesson preview
```

This makes the schedule feel explainable and trustworthy.

---

## 20. Button and Action Behavior at Product Level

The following actions should exist conceptually.

### Upload Syllabus

The user provides a syllabus file. StudyFlow extracts a course timeline.

### Use System Syllabus

The user selects a predefined syllabus template. StudyFlow uses it as the initial course timeline.

### Create Manual Lesson Plan

The user enters a simple week-by-week or lesson-by-lesson plan.

### Update Current Lesson

The user tells StudyFlow which lesson was most recently taught.

This updates which topics are considered taught, current, or future.

### Start Diagnostic Test

The user takes a short test for already taught topics.

The result initializes or updates mastery.

### Practice Latest Lesson

The system creates quiz or flashcard tasks for the most recently taught lesson.

### Review Previous Weak Topic

The system creates a review task for a topic already taught but still weak.

### Light Preview Next Lesson

The system creates a low-pressure preview task for the next lesson.

### Switch to Exam Sprint

The system changes behavior when the exam is within 14 days or when the user manually chooses exam sprint mode.

---

## 21. Important Product Rules for Codex

Codex should preserve these product rules when implementing the website.

### Rule 1: The syllabus controls the learning timeline

The system should not treat all document topics as immediately available.

### Rule 2: Materials provide learning content

Textbooks, PDFs, slides, and notes provide explanations, citations, quiz questions, and flashcards.

### Rule 3: Mapping connects lessons to materials

A syllabus lesson should be connected to textbook sections, slides, notes, or other sources.

### Rule 4: Continuous learning follows the classroom

Continuous mode should focus on the most recent lesson and previously taught topics.

### Rule 5: Untaught topics are blocked from full practice

Future topics should not receive full quizzes, flashcards, or mastery evaluation in continuous mode.

### Rule 6: Light preview is allowed

The next lesson may be previewed lightly, but it should not be treated as a full mastery task.

### Rule 7: Exam sprint starts at T-14 days

When the exam is within 14 days, continuous learning should shift to exam-focused preparation.

### Rule 8: Mid-semester users need diagnosis

If the student joins after several lessons have already happened, the system should offer a diagnostic test.

### Rule 9: Do not hardcode example courses

The system must work for many subjects, universities, syllabus formats, and document structures.

---

## 22. Example End-to-End Flow

This example is generic. Do not hardcode it.

A student creates a course.

They choose continuous semester learning.

They add a syllabus. The syllabus contains a week-by-week lesson plan.

They upload a textbook and lecture slides.

StudyFlow reads the syllabus and identifies the course timeline.

StudyFlow reads the materials and identifies chapters, sections, concepts, and explanations.

StudyFlow maps syllabus lessons to material sections.

The student says they are currently at Week 3.

StudyFlow identifies that Week 1 and Week 2 topics have already been taught.

StudyFlow suggests a short diagnostic test for those taught topics.

The student completes the diagnostic test.

StudyFlow learns that one topic from Week 2 is weak and one topic from Week 1 is strong.

StudyFlow creates a plan:

- Practice the current Week 3 lesson soon.
- Review the weak Week 2 topic tomorrow.
- Schedule light spaced repetition for the strong Week 1 topic.
- Avoid full practice for Week 4 topics because they have not been taught yet.
- Optionally preview Week 4 lightly before the next class.

Later, when the exam is 14 days away, StudyFlow switches the course to exam sprint behavior.

Now the system focuses on weak topics, important topics, past exam questions, mock tests, and final review.

---

## 23. Expected User Experience

The user should feel that StudyFlow understands their real academic situation.

The system should feel like it knows:

- What course the student is taking.
- What the university is teaching each week.
- What the student has already learned.
- What the student just learned.
- What the student has not learned yet.
- What needs review.
- When exam preparation should begin.

This makes StudyFlow different from a generic AI chatbot or a simple flashcard app.

StudyFlow becomes a learning companion that follows the semester and then helps the student transition into exam preparation.

---

## 24. Final Summary for Codex

StudyFlow AI should be redesigned around a syllabus-aware learning model.

The syllabus is the source of truth for the teaching timeline. Learning materials are the source of truth for detailed content. The system should map the two together.

In continuous semester learning mode, StudyFlow should follow the classroom timeline. It should practice recently taught lessons, review previous weak topics, and avoid assigning future untaught topics as full learning tasks.

When the exam is within 14 days, or when the user chooses exam sprint mode, the system should switch to exam-focused preparation. At that point, it can use the full exam scope and prioritize weak topics, important topics, mock tests, past exams, and high-impact review.

If a student starts using StudyFlow in the middle of a semester, the system should use the syllabus to determine what has already been taught and offer a diagnostic test to estimate mastery before generating a personalized plan.

The product should remain generic. Do not hardcode any specific syllabus, university, course code, textbook, chapter name, or subject.
