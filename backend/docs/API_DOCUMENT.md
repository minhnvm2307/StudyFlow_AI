# StudyFlow AI — Backend API Document

Backend is built on **FastAPI** and **PostgreSQL 16** (via Docker) with asyncpg. All user preferences, subjects, topics, tasks, and review history persist in PostgreSQL.
All JSON request and response payloads use **camelCase** keys. Responses wrap outcomes with `"status": "success"` (or `"status": "error"`) at the top level.

**Base URL**: `http://localhost:4000`

---

## Global Conventions

| Component | Protocol | Description |
|---|---|---|
| **Authentication & Isolation** | Query Param | Append `?user_id={user_id}` (e.g. `user-demo`) to routes. |
| **Subject Context** | Query Param | Append `?subject_id={subject_id}` (e.g. `subject-abc123`) to routes. |
| **Response Format** | JSON | CamelCase keys (middleware converts snake_case db records). |
| **Success Wrap** | JSON | Root objects contain `"status": "success"`. |
| **Error Format** | HTTP | returns `{"detail": "error message"}` with status 4xx/5xx. |
| **CORS** | HTTP | CORS enabled for `*` origins (dev mode). |

---

## 1. Authentication API

### POST `/api/auth/register`
Creates a new user account with email + password.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Success Response (200):**
```json
{
  "id": "user-user-example-com",
  "email": "user@example.com",
  "onboardingStep": 0,
  "goalMode": null,
  "dailyGoalMinutes": 30,
  "studyDays": ["Mon", "Tue", "Wed", "Thu", "Fri"],
  "studyWindow": null,
  "quietHours": null,
  "mascotTone": "encouraging",
  "notifications": {},
  "xp": 0,
  "streak": 0,
  "fsrsCustomWeights": null,
  "fsrsTuning": {
    "lastRunAt": null,
    "lastRmse": null,
    "reviewCountAtLastRun": 0
  }
}
```

**Error (400):** `{"detail": "Email already registered"}`

---

### POST `/api/auth/login`
Authenticates existing users.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Success Response (200):** Same user profile payload as `register`.

**Error (401):** `{"detail": "Invalid email or password"}`

---

### POST `/api/auth/mock`
Dev-only passwordless authentication. Creates or retrieves a user by email/ID.

**Query Params:** `?user_id={user_id}` (optional)

**Request Body:**
```json
{
  "email": "demo@example.com",
  "mode": "signup" // or "login"
}
```

**Success Response (200):** Same user profile payload as `register`.

---

### POST `/api/onboarding?user_id={user_id}`
Updates study configuration/preferences during onboarding. Increments onboarding step (max 3).

**Request Body:**
```json
{
  "goalMode": "semester", // or "exam"
  "dailyGoalMinutes": 45,
  "studyDays": ["Mon", "Wed", "Fri"],
  "mascotTone": "cute" // "encouraging", "focused", "cute"
}
```

**Success Response (200):** Updated user profile payload.

---

## 2. Subjects API

### GET `/api/subjects?user_id={user_id}`
Retrieves all subjects owned by the user, including all nested topics and tasks.

**Success Response (200):**
```json
{
  "status": "success",
  "subject-abc123": {
    "id": "subject-abc123",
    "userId": "user-demo",
    "name": "Linear Algebra",
    "mode": "semester",
    "examDate": null,
    "weeklyGoalMinutes": 0,
    "dailyGoalMinutes": 30,
    "daysAvailable": ["Mon", "Wed", "Fri"],
    "isPriority": false,
    "coverageWarning": null,
    "topics": [
      {
        "id": "topic-la-1",
        "subjectId": "subject-abc123",
        "title": "Matrix Multiplication",
        "mastery": 45,
        "awaitingDiagnostic": false,
        "weak": false
      }
    ],
    "tasks": [
      {
        "id": "task-la-1",
        "subjectId": "subject-abc123",
        "topicId": "topic-la-1",
        "topicTitle": "Matrix Multiplication",
        "type": "quiz",
        "durationMinutes": 15,
        "reason": "Review due topic",
        "scheduledDate": "2026-06-16",
        "status": "ready"
      }
    ]
  }
}
```

---

### POST `/api/subjects?user_id={user_id}`
Creates a new subject.

**Request Body:**
```json
{
  "name": "Linear Algebra",
  "mode": "semester", // or "exam"
  "examDate": "2027-01-11", // optional
  "weeklyGoalMinutes": 0,
  "dailyGoalMinutes": 30,
  "isPriority": false // optional
}
```

**Success Response (200):**
```json
{
  "status": "success",
  "id": "subject-abc123",
  "userId": "user-demo",
  "name": "Linear Algebra",
  "mode": "semester",
  "examDate": "2027-01-11",
  "weeklyGoalMinutes": 0,
  "dailyGoalMinutes": 30,
  "daysAvailable": [],
  "isPriority": false,
  "coverageWarning": null,
  "topics": [],
  "tasks": []
}
```

---

### POST `/api/subjects/{subject_id}/update?user_id={user_id}`
Updates the attributes of a specific subject (e.g. name, mode, exam date, daily goal, priority), deletes future tasks, and triggers a rebuild of the study plan.

**Request Body:**
```json
{
  "name": "Advanced Linear Algebra", // optional
  "mode": "exam", // optional, "semester" or "exam"
  "examDate": "2027-02-15", // optional
  "dailyGoalMinutes": 45, // optional
  "isPriority": true // optional
}
```

**Success Response (200):**
```json
{
  "status": "success",
  "subject": { ...updated_subject_fields },
  "todayTasks": [ ...task_fields ],
  "readiness": 85.5,
  "streak": 3,
  "xp": 120,
  "coverageWarning": null,
  "mascotMessage": "Subject updated! Your study schedule has been updated."
}
```

---

### POST `/api/subjects/current/mode?user_id={user_id}`
Updates the study mode of the user's primary subject. Deletes future tasks and dirties plan.

**Request Body:**
```json
{
  "mode": "exam" // or "semester"
}
```

**Success Response (200):** `{ "status": "success", ...subject_fields }`

---

### POST `/api/subjects/current/retune?user_id={user_id}`
Updates exam schedule targets and triggers rebuild of the study plan.

**Request Body:**
```json
{
  "examDate": "2027-02-01",
  "mode": "exam"
}
```

**Success Response (200):** `{ "status": "success", ...dashboard_fields }`

---

## 3. Documents & Material Upload API

### POST `/api/documents/upload?user_id={user_id}&subject_id={subject_id}`
Uploads files (PDF, DOCX, TXT), extracts text structure, splits into topic chunks via LLM, and creates initial diagnostic study tasks.

**Request Body (Multipart Form-Data):**
- `file`: (binary payload)
- `subject_id`: (optional fallback subject ID)
- `user_id`: (optional fallback user ID)

**Success Response (200):**
```json
{
  "status": "success",
  "s3Url": "https://s3.bucket/path/to/file.pdf",
  "subject": { ...subject_fields },
  "topics": [
    {
      "id": "topic-chunk-1",
      "subjectId": "subject-abc",
      "title": "CAP Theorem",
      "mastery": 15,
      "awaitingDiagnostic": true
    }
  ],
  "tasks": [
    {
      "id": "task-diag-chunk-1",
      "topicTitle": "CAP Theorem",
      "type": "diagnostic",
      "durationMinutes": 15,
      "scheduledDate": "2026-06-16",
      "status": "ready"
    }
  ]
}
```

---

### POST `/api/documents/mock-upload?user_id={user_id}&subject_id={subject_id}`
Injects mock document data. Same parsing pipeline as real upload but without LLM overhead. Useful for rapid testing.

**Success Response (200):** Same payload shape as `/api/documents/upload`.

---

## 4. State & Dashboard API

### GET `/api/state?user_id={user_id}&subject_id={subject_id}`
Retrieves consolidated application state: user profile, dashboard (today's tasks, streak, XP), notification config, and achievements.

**Success Response (200):**
```json
{
  "status": "success",
  "profile": { ...profile_fields },
  "dashboard": {
    "subject": { ...subject_fields },
    "todayTasks": [ ...task_fields ],
    "readiness": 85.5,
    "streak": 3,
    "xp": 120,
    "coverageWarning": null,
    "mascotMessage": "Keep going!"
  },
  "notifications": [ ...notification_objects ],
  "achievements": [ ...achievement_objects ]
}
```

---

### GET `/api/dashboard?user_id={user_id}&subject_id={subject_id}`
Gets dashboard statistics and today's tasks for a specific subject.

**Success Response (200):** `{ "status": "success", ...dashboard_fields }`

---

### GET `/api/plan/weekly?user_id={user_id}&subject_id={subject_id}`
Returns all scheduled tasks for the week. If `subject_id=all` (or empty), retrieves combined tasks across all subjects. If plan is dirty, triggers a background schedule rebuild before returning.

**Success Response (200):**
```json
{
  "status": "success",
  "coverageWarning": null,
  "tasks": [
    {
      "id": "task-la-1",
      "subjectId": "subject-abc",
      "subjectName": "Linear Algebra",
      "topicId": "topic-la-1",
      "topicTitle": "Matrix Multiplication",
      "type": "review",
      "durationMinutes": 20,
      "reason": "Retain mastery level",
      "scheduledDate": "2026-06-16",
      "status": "ready",
      "day": "Tue"
    }
  ]
}
```

**Special Status Responses:**
* `"status": "locked"` — A schedule generation process is currently running.
* `"status": "infeasible"` — Time constraint/deadline conflict (cannot schedule all topics).

---

## 5. Session & Practice API

### POST `/api/tasks/{task_id}/session?user_id={user_id}&force_regenerate={true|false}`
Generates questions for a study session. Diagnostic tasks contain 5 questions, regular review/quiz tasks contain 3.
* **Date Guardrail**: If `task.scheduledDate` is in the future (`> today`), returns **400 Bad Request**.

**Query Params:**
- `force_regenerate`: (boolean) Force fresh question generation via LLM instead of reusing past database records.

**Success Response (200):**
```json
{
  "status": "success",
  "id": "session-uuid",
  "subjectId": "subject-abc",
  "taskId": "task-la-1",
  "isDiagnostic": false,
  "questions": [
    {
      "id": "topic-abc-q1",
      "sessionId": "session-uuid",
      "topicId": "topic-abc",
      "prompt": "What is consistency in CAP theorem?",
      "options": ["A: Consistent response", "B: Constant delay", "C: Partition tolerance", "D: All of the above"],
      "correctOption": "A: Consistent response",
      "explanation": "Consistency means every read receives the most recent write or an error.",
      "source": "",
      "selectedOption": null,
      "isCorrect": null,
      "reported": false
    }
  ],
  "submittedAt": null,
  "correct": null,
  "total": null,
  "xpEarned": null,
  "feedback": null
}
```

**Error Responses:**
* **400 Bad Request**: `{"detail": "Cannot study future tasks"}` (attempting to study ahead).
* **404 Not Found**: `{"detail": "Task not found"}` or `{"detail": "Topic not found"}`.

---

### POST `/api/sessions/{session_id}/submit?user_id={user_id}`
Submits user answers to be graded. Updates BKT mastery levels, schedules future cards with FSRS, awards XP.

**Request Body:**
```json
{
  "rating": "Good", // optional FSRS rating: "Again", "Hard", "Good", "Easy"
  "answers": [
    {
      "questionId": "topic-abc-q1",
      "selectedOption": "A: Consistent response",
      "reported": false
    }
  ]
}
```

**Success Response (200):**
```json
{
  "status": "success",
  "sessionId": "session-uuid",
  "correct": 1,
  "total": 1,
  "xpEarned": 10,
  "masteryDelta": [
    { "topicId": "topic-abc", "delta": 15 }
  ],
  "nextTask": null,
  "feedback": "Great job! 1/1 correct."
}
```

---

### POST `/api/session/update-budget?user_id={user_id}`
Rescales today's study budget (redistributes tasks to match the target daily minutes).

**Request Body:**
```json
{
  "dailyGoalMinutes": 45
}
```

**Success Response (200):** `{ "status": "success", "todayTasks": [ ...updated_tasks ] }`

---

## 6. Exam & Readiness API

### POST `/api/exam-plan?user_id={user_id}`
Switches primary subject study mode to `exam_sprint`, configures the deadline date, and rebuilds the schedule.

**Request Body:**
```json
{
  "examDate": "2027-01-11",
  "dailyMinutes": 45
}
```

**Success Response (200):** `{ "status": "success", ...dashboard_fields }`

---

### GET `/api/readiness/checklist?user_id={user_id}&subject_id={subject_id}`
Evaluates subject exam preparedness (topics covered, mastery percentage, diagnostic completion).

**Success Response (200):**
```json
{
  "status": "success",
  "readiness": 85.0,
  "disclaimer": "Readiness is an estimate based on mastery scores.",
  "items": [
    { "id": "topics_covered", "label": "All topics covered", "done": true },
    { "id": "mastery_above_60", "label": "Average mastery > 60%", "done": false },
    { "id": "no_diagnostic_pending", "label": "No pending diagnostics", "done": true }
  ]
}
```

---

### POST `/api/mock-test/complete?user_id={user_id}`
Completes a mock test session. Identifies the weakest topic and boosts its mastery by 6%.

**Success Response (200):** `{ "status": "success", "topicUpdated": { ...topic_fields } }`

---

### POST `/api/recovery/apply?user_id={user_id}`
Applies recovery scheduling: converts all past `"missed"` tasks to `"ready"`, reschedules them to today, and caps their duration at 20 minutes each.

**Success Response (200):** `{ "status": "success", ...dashboard_fields }`

---

## 7. Miscellaneous API

### POST `/api/chat?user_id={user_id}`
Queries AI study companion.

**Request Body:**
```json
{
  "messages": [
    { "role": "user", "content": "Explain CAP Theorem simply." }
  ]
}
```

**Success Response (200):**
```json
{
  "status": "success",
  "provider": "openai",
  "message": { "role": "assistant", "content": "CAP theorem states..." },
  "sources": []
}
```

---

### POST `/api/settings?user_id={user_id}`
Updates notification and mascot preferences.
* *Note*: Request fields use **snake_case** keys directly.

**Request Body:**
```json
{
  "mascot_tone": "cute",
  "quiet_hours": {
    "start": "22:00",
    "end": "07:00"
  }
}
```

**Success Response (200):** `{ "status": "success", ...profile_fields }`

---

### POST `/api/notifications/{notification_id}?user_id={user_id}`
Toggles user notification settings by ID.

**Request Body:**
```json
{
  "enabled": true
}
```

**Success Response (200):** `{ "status": "success", "id": "notif-id", "enabled": true }`

---

### POST `/api/leaderboard/join?user_id={user_id}`
Registers user to the global study leaderboard and returns the leaderboard rank and entries.

**Success Response (200):**
```json
{
  "status": "success",
  "rank": 1,
  "entries": [
    { "name": "user-demo", "xp": 120, "rank": 1 }
  ]
}
```

---

### POST `/api/after-class-content?user_id={user_id}`
Injects an ad-hoc topic chunk/note immediately after class, creating a task to study it today.

**Request Body:**
```json
{
  "title": "Lecture Notes - Matrices",
  "source": "A matrix is a rectangular array of numbers..."
}
```

**Success Response (200):** `{ "status": "success", "topic": { ...topic_fields }, "task": { ...task_fields } }`

---

## 8. FSRS Tuning API

### GET `/api/fsrs/tuning/status?user_id={user_id}`
Gets the number of accumulated flashcard review log entries and whether FSRS weight optimization can run (threshold is 1,000 logs).

**Success Response (200):**
```json
{
  "status": "success",
  "reviewCount": 42,
  "threshold": 1000,
  "lastRunAt": null,
  "lastRmse": null,
  "reviewCountAtLastRun": 0
}
```

---

### POST `/api/fsrs/tuning/run?user_id={user_id}`
Runs optimization of FSRS card scheduling weights on the user review logs.

**Success Response (200):**
```json
{
  "status": "success",
  "weights": [0.4, 0.6, 1.2, 1.5, 0.5, 0.9, 1.1, 0.2, 1.6, 0.8, 1.3, 0.7, 0.3, 0.4, 1.1, 0.8, 1.4],
  "rmse": 0.082,
  "reviewCount": 1150,
  "applied": true
}
```
