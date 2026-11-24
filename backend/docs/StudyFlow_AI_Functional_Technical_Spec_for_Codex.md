# StudyFlow AI — Functional & Technical Spec for Codex

> **Mục đích:** Tài liệu này dùng cho Codex để biến UI prototype StudyFlow AI thành website hoạt động đầy đủ ở mức MVP.  
> **Phạm vi:** Mô tả cách hệ thống hoạt động, đặc tả chức năng, cách button/action hoạt động, yêu cầu kỹ thuật frontend/backend, API, data model, state flow và acceptance criteria.  
> **Target:** Web app cho desktop/laptop browser. Không làm mobile app.  
> **Ưu tiên:** Build được end-to-end flow với mock data/local data trước, sau đó có thể nối backend/AI/RAG thật.

---

## 0. Product Summary

**StudyFlow AI** là web app trợ lý học tập cho sinh viên.

Người dùng có thể:

1. Tạo môn học.
2. Nhập mục tiêu, ngày thi, lịch trống.
3. Upload hoặc thêm tài liệu môn học.
4. Hệ thống phân tích tài liệu thành topic/module.
5. Hệ thống tạo lịch học.
6. Người dùng học bằng quiz, flashcard, chatbot.
7. Hệ thống cập nhật mastery theo topic.
8. Nếu người dùng học chậm/bỏ lỡ/kết quả thấp, hệ thống gợi ý lập lại lịch.

---

## 1. Codex Implementation Goal

Codex cần biến UI hiện tại thành website có chức năng thật ở mức MVP.

### 1.1 End-to-end flow cần chạy được

```text
User mở app
→ Dashboard hiển thị task hôm nay
→ User tạo môn học mới
→ User thêm hoặc bỏ qua tài liệu
→ Hệ thống tạo topic map giả lập hoặc thật
→ Hệ thống tạo lịch học
→ User xem page Môn học
→ User mở Lịch học
→ User click event học
→ User bắt đầu quiz/flashcard hoặc mở chatbot
→ User hỏi chatbot theo tài liệu
→ User làm quiz
→ User xem kết quả
→ User bấm "Hỏi AI giải thích"
→ Chatbot mở với context câu sai
→ User bấm "Lập lại lịch" nếu bỏ lỡ task
```

### 1.2 Mức hoàn thiện

#### Level 1 — Functional Prototype

- Dùng mock data/localStorage.
- Không cần backend thật.
- Button hoạt động bằng state nội bộ.
- Có routing giữa các page.
- Có modal/popover.
- Có fake quiz, fake flashcard, fake chat response.

#### Level 2 — Local Fullstack MVP

- Có backend API.
- Có database local.
- Upload file thật.
- Lưu course, source, task, chat, quiz result.
- Có fake AI hoặc AI API đơn giản.
- Scheduler tạo task dựa trên input.

#### Level 3 — AI/RAG MVP

- File upload được parse/chunk/embed.
- Chatbot trả lời bằng RAG.
- Quiz/flashcard sinh từ tài liệu.
- Citations trỏ về source.
- Mastery cập nhật theo kết quả luyện tập.

Codex nên ưu tiên Level 1 trước, nhưng tổ chức code để dễ nâng lên Level 2/3.

---

## 2. Recommended Technical Stack

### 2.1 Frontend

Đề xuất:

```text
React + Vite
React Router
CSS Modules / plain CSS / Tailwind nếu project đã dùng
Context / Zustand / Redux Toolkit nếu cần state management
```

Yêu cầu:

- Tách page component rõ ràng.
- Tách shared components.
- Tách mock data.
- Tách API/service layer để sau này thay mock bằng backend.
- Không gọi `fetch` trực tiếp rải rác trong component.

### 2.2 Backend

Có thể chọn một trong hai.

#### Option A — Node.js / Express

```text
Node.js
Express
Prisma hoặc Mongoose
SQLite/PostgreSQL/MongoDB
Multer cho upload file
```

#### Option B — Python / FastAPI

```text
FastAPI
SQLAlchemy
SQLite/PostgreSQL
LangChain hoặc LlamaIndex nếu cần RAG
Chroma/FAISS/Qdrant cho vector store
```

### 2.3 Database

MVP local:

```text
SQLite hoặc localStorage
```

MVP triển khai thật:

```text
PostgreSQL
```

Vector store:

```text
Chroma hoặc FAISS local
Qdrant nếu deploy nghiêm túc
```

---

## 3. High-level Architecture

```text
Frontend React
│
├── Dashboard
├── Courses
├── Schedule
├── Study Workspace / Chatbot
├── Onboarding
├── Quiz
├── Flashcard
└── Results
│
API Client Layer
│
Backend API / Mock Service
│
├── Course Service
├── Source/File Service
├── Topic Map Service
├── Schedule Service
├── Practice Service
├── Chat/RAG Service
├── Mastery Service
└── Reschedule Service
│
Database / localStorage
│
├── users
├── courses
├── sources
├── topics
├── study_tasks
├── flashcards
├── quizzes
├── quiz_results
├── chat_threads
├── chat_messages
└── mastery_records
│
Vector Store, optional
│
└── document chunks + embeddings
```

---

## 4. Core Data Models

### 4.1 User

```ts
type User = {
  id: string;
  name: string;
  email?: string;
  avatarUrl?: string;
};
```

### 4.2 Course

```ts
type Course = {
  id: string;
  userId: string;
  name: string;
  mode: "continuous" | "exam_sprint";
  targetScore?: number;
  examDate?: string;
  priority: "low" | "medium" | "high";
  status: "on_track" | "needs_attention" | "behind" | "not_enough_data";
  masteryPercent: number;
  readinessPercent?: number;
  sourceCount: number;
  createdAt: string;
  updatedAt: string;
};
```

### 4.3 Source

```ts
type Source = {
  id: string;
  courseId: string;
  filename: string;
  fileType: "pdf" | "docx" | "pptx" | "txt" | "web" | "exam" | "answer";
  status: "uploading" | "parsing" | "ready" | "failed";
  selected: boolean;
  topicCount: number;
  errorMessage?: string;
  createdAt: string;
};
```

### 4.4 Topic

```ts
type Topic = {
  id: string;
  courseId: string;
  name: string;
  moduleName: string;
  description?: string;
  masteryPercent: number;
  importance: "low" | "medium" | "high";
  status: "weak" | "needs_review" | "good" | "unknown";
  dueReviewAt?: string;
};
```

### 4.5 StudyTask

```ts
type StudyTask = {
  id: string;
  courseId: string;
  topicId?: string;
  title: string;
  type: "quiz" | "flashcard" | "review" | "qa" | "mock_test";
  startAt: string;
  endAt: string;
  durationMinutes: number;
  status: "todo" | "in_progress" | "done" | "missed" | "rescheduled";
  priority: "low" | "medium" | "high";
  reason?: string;
};
```

### 4.6 Quiz

```ts
type Quiz = {
  id: string;
  courseId: string;
  topicId?: string;
  title: string;
  questions: QuizQuestion[];
  createdAt: string;
};

type QuizQuestion = {
  id: string;
  question: string;
  options: string[];
  correctAnswer: string;
  explanation: string;
  topicId?: string;
  sourceRef?: SourceReference;
};
```

### 4.7 QuizResult

```ts
type QuizResult = {
  id: string;
  quizId: string;
  courseId: string;
  score: number;
  total: number;
  accuracyPercent: number;
  averageSecondsPerQuestion: number;
  mistakes: QuizMistake[];
  createdAt: string;
};

type QuizMistake = {
  questionId: string;
  topicName: string;
  question: string;
  selectedAnswer: string;
  correctAnswer: string;
  explanation: string;
  sourceRef?: SourceReference;
};
```

### 4.8 Flashcard

```ts
type Flashcard = {
  id: string;
  courseId: string;
  topicId: string;
  front: string;
  back: string;
  explanation?: string;
  sourceRef?: SourceReference;
  dueAt?: string;
  lastRating?: "again" | "hard" | "good" | "easy";
};
```

### 4.9 Chat

```ts
type ChatThread = {
  id: string;
  courseId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  origin?: "normal" | "quiz_result" | "flashcard" | "source";
};

type ChatMessage = {
  id: string;
  threadId: string;
  role: "user" | "assistant" | "system";
  content: string;
  sourceRefs?: SourceReference[];
  actions?: ChatAction[];
  createdAt: string;
};

type SourceReference = {
  sourceId: string;
  filename: string;
  page?: number;
  section?: string;
  quote?: string;
};

type ChatAction = {
  label: string;
  type: "generate_flashcards" | "generate_quiz" | "add_to_schedule" | "explain_simpler";
  payload?: Record<string, unknown>;
};
```

---

## 5. Routes

```text
/                       -> Dashboard
/dashboard              -> Dashboard
/courses                -> Môn học
/courses/new            -> Onboarding tạo môn học
/schedule               -> Lịch học
/study/:courseId        -> Study Workspace / Chatbot
/practice/quiz/:quizId  -> Quiz session
/practice/results/:id   -> Quiz results
/practice/flashcards/:sessionId -> Flashcard session
```

---

# 6. Dashboard Page

## 6.1 Purpose

Dashboard hiển thị overview học tập hôm nay:

- Task ưu tiên.
- Task hôm nay.
- Course progress.
- Weak topics.
- Due reviews.
- Weekly stats.
- Deadline gần nhất.

## 6.2 Data Needed

Endpoint tổng hợp:

```text
GET /api/dashboard
```

Response:

```ts
type DashboardResponse = {
  user: User;
  todayTasks: StudyTask[];
  courses: Course[];
  weakTopics: Topic[];
  weeklyStats: {
    progressPercent: number;
    completedTasks: number;
    totalTasks: number;
    minutesStudied: number;
    streakDays: number;
  };
  nearestDeadline?: {
    courseId: string;
    courseName: string;
    label: string;
  };
  nextSchedule?: StudyTask;
};
```

## 6.3 Button Behavior

### `Bắt đầu học`

Location: Focus Card.

Behavior:

```text
If focus task type = quiz:
  Navigate to /practice/quiz/:quizId or create quiz session first.

If focus task type = flashcard:
  Navigate to /practice/flashcards/:sessionId.

If focus task type = qa:
  Navigate to /study/:courseId with suggested prompt/context.

If focus task type = review:
  Navigate to /study/:courseId or /courses/:courseId.
```

MVP mock:

```text
Click → route to matching mock page or show toast.
```

### `Xem lý do`

Behavior:

```text
Open popover/modal explaining why this task is recommended.
```

Example:

```text
Task này được ưu tiên vì topic "Không gian vector" có mastery 42% và kỳ thi còn 12 ngày.
```

### `Làm ngay` / `Ôn ngay` / `Mở chatbot`

Behavior:

```text
Same as Bắt đầu học, based on task type.
```

### `Ôn flashcards`

```text
Navigate to /practice/flashcards/:sessionId.
```

### `Xem lịch`

```text
Navigate to /schedule.
```

### Course row click

```text
Navigate to /study/:courseId or /courses/:courseId.
Recommended MVP: /study/:courseId.
```

## 6.4 State Rules

- Nếu chưa có courses: show empty state + `Thêm môn học`.
- Nếu chưa có tasks hôm nay: show empty state + `Tạo lịch học`.
- Nếu có missed tasks: show recovery alert + `Lập lại lịch`.

## 6.5 Acceptance Criteria

- Dashboard load từ API/mock.
- Buttons route/open modal đúng.
- Empty states đầy đủ.
- Focus task lấy từ highest priority task.
- Stats update sau khi complete task.

---

# 7. Courses Page

## 7.1 Purpose

Trang `Môn học` quản lý tất cả course/study notebooks theo phong cách NotebookLM gallery.

## 7.2 Data Needed

```text
GET /api/courses
GET /api/courses?filter=featured
GET /api/courses?sort=recent
```

## 7.3 Button and Interaction Behavior

### `+ Tạo mới`

```text
Navigate to /courses/new.
```

### Card `Tạo môn học mới`

```text
Navigate to /courses/new.
```

### Click Course Card

Recommended MVP:

```text
Navigate to /study/:courseId.
```

Alternative:

```text
Navigate to /courses/:courseId if course detail exists.
```

### Filter Tabs

Tabs:

```text
Tất cả
Môn học của tôi
Môn học nổi bật
Được chia sẻ với tôi
```

Behavior:

```text
Set activeFilter state.
Filter displayed courses client-side in MVP.
```

Rules:

- `Tất cả`: show all courses.
- `Môn học của tôi`: show courses owned by current user.
- `Môn học nổi bật`: courses with high priority, needs_attention, or exam soon.
- `Được chia sẻ với tôi`: show shared courses or empty state.

### Search

```text
Filter courses by name.
```

### Sort Dropdown

Options:

```text
Gần đây nhất
Tên A-Z
Sắp thi nhất
Cần chú ý
```

Behavior:

```text
Sort courses client-side.
```

### Grid/List Toggle

MVP:

```text
Toggle between grid view and compact list view.
```

If not fully implemented:

```text
At least update active icon state.
```

### Course Card Menu `⋮`

Actions:

```text
Đổi tên
Ghim
Chia sẻ
Xóa
```

MVP behavior:

- `Đổi tên`: open rename modal.
- `Ghim`: toggle featured/pinned state.
- `Chia sẻ`: open share modal or toast.
- `Xóa`: confirm modal then remove from state.

## 7.4 Empty States

### No courses

```text
Bạn chưa có môn học nào.
Tạo môn học đầu tiên để StudyFlow lập lịch học, quiz và flashcard cho bạn.
[Tạo môn học mới]
```

### No shared courses

```text
Chưa có môn học nào được chia sẻ với bạn.
```

## 7.5 Acceptance Criteria

- Courses load from mock/API.
- Create new button works.
- Course card click routes to workspace/detail.
- Filter/search/sort work client-side.
- Course menu actions have visible feedback.

---

# 8. Onboarding Create Course

## 8.1 Route

```text
/courses/new
```

## 8.2 MVP Scope

Hiện tại có thể implement screen đầu tiên `Thông tin môn`, nhưng code nên chuẩn bị state cho 4 bước.

Recommended steps:

```text
Step 1: Thông tin môn
Step 2: Mục tiêu & lịch
Step 3: Tài liệu
Step 4: Xác nhận
```

## 8.3 Course Creation Flow

```text
User nhập tên môn
→ chọn mode
→ chọn priority
→ nhập target/exam/schedule
→ upload hoặc skip tài liệu
→ confirm
→ POST /api/courses
→ POST /api/sources nếu có file
→ POST /api/courses/:id/generate-plan
→ route to /study/:courseId hoặc /dashboard
```

## 8.4 Step Fields

### Step 1

```text
Tên môn học
Chế độ học: continuous | exam_sprint
Mức độ ưu tiên: low | medium | high
```

### Step 2

```text
Ngày thi
Target điểm
Thời lượng học mỗi phiên
Lịch trống trong tuần
```

### Step 3

```text
Upload files
Add website link
Paste text
Skip temporarily
```

### Step 4

Show summary:

```text
Môn học
Chế độ
Ngày thi
Target
Ưu tiên
Số tài liệu
Lịch trống
Topic map preview
```

## 8.5 Button Behavior

### `Hủy`

```text
Navigate back to /courses.
If form dirty, show confirm: "Bạn có chắc muốn hủy?"
```

### `Tiếp tục`

```text
Validate current step.
If valid: go to next step.
If invalid: show inline error.
```

Step 1 validation:

```text
Course name required.
Mode required.
Priority required.
```

### `Quay lại`

```text
Go to previous step.
```

### `Bỏ qua tạm thời`

Location: Step 3.

```text
Proceed to Step 4 without sources.
Show note: "Bạn có thể thêm tài liệu sau."
```

### `Tạo kế hoạch học`

```text
Create course.
Generate initial topics/tasks.
Navigate to /study/:courseId.
```

## 8.6 API Endpoints

```text
POST /api/courses
POST /api/courses/:courseId/sources
POST /api/courses/:courseId/generate-topic-map
POST /api/courses/:courseId/generate-plan
```

## 8.7 Acceptance Criteria

- Form state persists between steps.
- Validation works.
- Course can be created.
- Created course appears on Courses page and Dashboard.
- If files are skipped, course still exists.

---

# 9. Schedule Page

## 9.1 Route

```text
/schedule
```

## 9.2 Purpose

Lịch học theo phong cách Google Calendar.

Người dùng có thể:

- Xem task theo tuần/ngày/tháng/agenda.
- Click task để xem chi tiết.
- Tạo nhiệm vụ học thủ công.
- Dời lịch task.
- Lập lại lịch nếu có task missed.

## 9.3 Data Needed

```text
GET /api/tasks?start=...&end=...
GET /api/courses
```

## 9.4 Button and Interaction Behavior

### `Hôm nay`

```text
Set calendar date to today.
```

### Previous / Next

```text
If view = week: move by 1 week.
If view = day: move by 1 day.
If view = month: move by 1 month.
```

### View Switcher

Buttons:

```text
Ngày
Tuần
Tháng
Lịch biểu
```

Behavior:

```text
Set currentCalendarView.
Render corresponding view.
```

MVP requirement:

- Week view required.
- Agenda view recommended.
- Day/month can be simple placeholder or simple grid.

### `+ Tạo nhiệm vụ học`

```text
Open CreateTaskModal.
```

### `Lưu nhiệm vụ`

Inside CreateTaskModal.

```text
Validate title, course, type, start/end.
Create task in state/API.
Close modal.
Show task in calendar.
```

API:

```text
POST /api/tasks
```

### Click Event Block

```text
Open EventDetailPopover.
```

Popover actions:

#### `Bắt đầu học`

```text
If task type quiz: create/open quiz session.
If flashcard: create/open flashcard session.
If qa: open /study/:courseId with prompt context.
If review: open /study/:courseId or course detail.
```

#### `Dời lịch`

```text
Open single-task reschedule modal.
User chooses new date/time.
PATCH /api/tasks/:taskId.
```

#### `Xem môn`

```text
Navigate to /study/:courseId.
```

### Course filters

```text
Checkbox course filters toggle event visibility by course.
```

### Task type filters

```text
Checkbox task type filters toggle event visibility by type.
```

### `Lập lại lịch`

```text
Open RescheduleModal for missed tasks.
```

## 9.5 Reschedule Modal Behavior

Options:

```text
Giữ khối lượng
Tăng cường độ
Cắt giảm phạm vi ít quan trọng
Ưu tiên theo môn
```

Button `Áp dụng lịch mới`:

```text
POST /api/schedule/reschedule
Update task list.
Close modal.
Show toast.
```

## 9.6 Acceptance Criteria

- Week view renders events.
- Filters work.
- Event popover opens.
- Create task modal works.
- Reschedule modal opens.
- Calendar updates after create/reschedule.

---

# 10. Study Workspace / Chatbot

## 10.1 Route

```text
/study/:courseId
```

## 10.2 Purpose

Workspace giống NotebookLM.

Người dùng:

- Chọn nguồn tài liệu.
- Xem lịch sử chat.
- Hỏi AI.
- Nhận câu trả lời có citations.
- Tạo quiz/flashcard/study guide từ Studio.
- Mở context từ quiz mistake.

## 10.3 Data Needed

```text
GET /api/courses/:courseId
GET /api/courses/:courseId/sources
GET /api/courses/:courseId/chat-threads
GET /api/chat-threads/:threadId/messages
```

## 10.4 Top Bar Buttons

### `+ Tạo ghi chú`

```text
Create note from current conversation or open note composer.
MVP: show toast "Đã tạo ghi chú mẫu".
```

### `Số liệu phân tích`

```text
Open analytics panel/modal for course progress.
MVP: show mastery, source count, chat count, quiz stats.
```

### `Chia sẻ`

```text
Open share modal.
```

### `Cài đặt`

```text
Open workspace settings modal.
```

## 10.5 Left Sidebar — Tab Nguồn

### `+ Thêm nguồn`

```text
Open add source modal.
```

Options:

```text
Upload file
Paste website
Paste text
Google Drive placeholder
```

### Source Checkbox

```text
Toggle source.selected.
Selected sources are used for chat retrieval.
```

### Source Search

```text
Filter source list by filename.
```

### Source Menu `⋮`

Actions:

```text
Xem chi tiết
Đổi tên
Xóa nguồn
```

MVP:

- `Xem chi tiết`: open modal.
- `Đổi tên`: open rename modal.
- `Xóa nguồn`: confirm and remove.

## 10.6 Left Sidebar — Tab Lịch sử chat

### Search

```text
Filter chat threads by title.
```

### Click Chat Thread

```text
Load selected thread messages in Conversation Panel.
Set active thread.
```

### `+ Cuộc trò chuyện mới`

```text
Create new empty chat thread.
Clear conversation.
```

## 10.7 Conversation Panel

### Empty State Buttons

```text
Hỏi về tài liệu
Tạo quiz từ nguồn
Tạo flashcards
```

Behavior:

- `Hỏi về tài liệu`: focus chat input.
- `Tạo quiz từ nguồn`: trigger Studio quiz action.
- `Tạo flashcards`: trigger Studio flashcard action.

### Chat Input

On send:

```text
Add user message.
Call POST /api/chat or mockChatService.sendMessage.
Show loading.
Add assistant response.
```

Request:

```ts
{
  courseId: string;
  threadId?: string;
  message: string;
  selectedSourceIds: string[];
  context?: {
    type: "quiz_mistake" | "flashcard" | "normal";
    payload: any;
  };
}
```

Response:

```ts
{
  threadId: string;
  answer: string;
  sourceRefs: SourceReference[];
  actions: ChatAction[];
}
```

### Assistant Action Buttons

Actions:

```text
Tạo 5 flashcards
Ra 3 câu quiz
Thêm vào lịch ôn
Giải thích dễ hơn
```

Behavior:

- `Tạo 5 flashcards`: generate flashcards and show toast/open flashcard session.
- `Ra 3 câu quiz`: generate quiz and route to quiz session.
- `Thêm vào lịch ôn`: open create task modal prefilled.
- `Giải thích dễ hơn`: auto-send follow-up prompt.

## 10.8 Studio Panel

Cards:

```text
Tạo quiz
Tạo flashcard
Study guide
Bản đồ tư duy
Checklist ôn thi
Mock test
Báo cáo học tập
Tóm tắt topic yếu
```

Behavior:

- `Tạo quiz`: generate/open quiz.
- `Tạo flashcard`: generate/open flashcard session.
- `Study guide`: show generated study guide in Studio output area.
- `Bản đồ tư duy`: show text/visual mindmap placeholder.
- `Checklist ôn thi`: generate checklist.
- `Mock test`: generate mock test quiz.
- `Báo cáo học tập`: open report modal.
- `Tóm tắt topic yếu`: show weak topics + recommended actions.

## 10.9 Chat from Quiz Mistake

When user clicks `Hỏi AI giải thích` from Results:

```text
Navigate to /study/:courseId?context=quiz_mistake&questionId=...
```

Behavior:

```text
Load workspace.
Create/open chat thread.
Show Context Card at top of Conversation Panel.
Auto-fill or auto-send prompt:
"Giải thích vì sao đáp án của tôi sai và cách nhớ đúng."
```

## 10.10 Acceptance Criteria

- Tab Nguồn/Lịch sử chat works.
- Source selection state works.
- Chat input sends message and displays response.
- Assistant response has citations and action buttons.
- Studio buttons trigger visible behavior.
- Quiz mistake context works.

---

# 11. Quiz Feature

## 11.1 Routes

```text
/practice/quiz/:quizId
/practice/results/:resultId
```

## 11.2 Quiz Session Behavior

```text
Open quiz
→ answer questions
→ next question
→ submit
→ calculate score
→ save result
→ show Results page
```

Required UI state:

```ts
currentQuestionIndex
selectedAnswer
answersByQuestionId
timeSpentByQuestionId
markedForReview
```

## 11.3 Buttons

### `Câu tiếp theo`

```text
Save selected answer.
Move to next question.
If last question: show "Nộp bài".
```

### `Đánh dấu xem lại`

```text
Toggle markedForReview for current question.
```

### `Nộp bài`

```text
Calculate result.
POST /api/quiz-results or save to local store.
Navigate to /practice/results/:resultId.
```

## 11.4 Results Buttons

### `Hỏi AI giải thích`

```text
Navigate to /study/:courseId with quiz mistake context.
```

### `Xem source`

```text
Open source reference modal.
```

### `Ra câu tương tự`

```text
Generate short quiz with same topic.
```

### `Tiếp tục luyện`

```text
Generate another quiz or route to Study Workspace.
```

---

# 12. Flashcard Feature

## 12.1 Route

```text
/practice/flashcards/:sessionId
```

## 12.2 Behavior

```text
Show front card
→ user clicks Lật thẻ
→ show back card
→ user rates Again/Hard/Good/Easy
→ update card review state
→ next card
→ session summary
```

## 12.3 Buttons

### `Lật thẻ`

```text
Set isFlipped = true.
```

### `Again` / `Hard` / `Good` / `Easy`

```text
Save rating.
Update review schedule.
Move to next card.
```

### `Hỏi AI giải thích`

```text
Navigate to /study/:courseId with flashcard context.
```

### `Tạo quiz tương tự`

```text
Generate quiz from flashcard topic.
```

### `Kết thúc phiên`

```text
Show flashcard session summary.
```

---

# 13. Scheduling Logic

## 13.1 Initial Plan Generation

When course is created, generate tasks based on:

```text
course mode
exam date
target score
priority
availability
sources/topics
```

Simple MVP algorithm:

```ts
For each weak/unknown topic:
  create quiz task
  create flashcard task
  assign to available time slots
  prioritize high importance topics
  if exam_sprint, schedule more frequent review
```

## 13.2 Task Priority Factors

```text
Topic mastery low
Exam date near
Course priority high
Task missed before
Topic importance high
```

## 13.3 Reschedule Logic

Trigger reschedule when:

```text
task status = missed
quiz accuracy < 60%
exam date changed
availability changed
target score changed
```

MVP reschedule:

```text
Move missed tasks to next available slots.
If workload too high, show warning.
```

Advanced:

```text
Recalculate topic coverage.
Prioritize important/weak topics.
Reduce low-priority tasks if needed.
```

---

# 14. Backend API Specification

Codex can implement these endpoints or keep service layer ready.

## 14.1 Courses

```text
GET    /api/courses
GET    /api/courses/:courseId
POST   /api/courses
PATCH  /api/courses/:courseId
DELETE /api/courses/:courseId
```

## 14.2 Sources

```text
GET    /api/courses/:courseId/sources
POST   /api/courses/:courseId/sources
PATCH  /api/sources/:sourceId
DELETE /api/sources/:sourceId
POST   /api/sources/:sourceId/parse
```

## 14.3 Topics

```text
GET    /api/courses/:courseId/topics
POST   /api/courses/:courseId/generate-topic-map
PATCH  /api/topics/:topicId
```

## 14.4 Schedule / Tasks

```text
GET    /api/tasks
GET    /api/tasks/today
POST   /api/tasks
PATCH  /api/tasks/:taskId
DELETE /api/tasks/:taskId
POST   /api/schedule/generate
POST   /api/schedule/reschedule
```

## 14.5 Chat

```text
GET    /api/courses/:courseId/chat-threads
POST   /api/chat-threads
GET    /api/chat-threads/:threadId/messages
POST   /api/chat
DELETE /api/chat-threads/:threadId
```

## 14.6 Quiz

```text
POST   /api/quizzes/generate
GET    /api/quizzes/:quizId
POST   /api/quiz-results
GET    /api/quiz-results/:resultId
```

## 14.7 Flashcards

```text
POST   /api/flashcards/generate
GET    /api/courses/:courseId/flashcards
POST   /api/flashcard-sessions
PATCH  /api/flashcards/:flashcardId/review
```

## 14.8 Dashboard

```text
GET    /api/dashboard
```

---

# 15. Frontend Service Layer

Create service functions so UI does not call fetch directly everywhere.

Example:

```ts
coursesApi.getCourses();
coursesApi.createCourse(payload);
tasksApi.getTodayTasks();
tasksApi.createTask(payload);
chatApi.sendMessage(payload);
quizApi.generateQuiz(payload);
flashcardApi.generateFlashcards(payload);
scheduleApi.reschedule(payload);
```

For MVP, these functions can read/write local mock store. Later, replace implementation with real HTTP calls.

---

# 16. Local Storage MVP Option

If no backend yet, persist data in localStorage.

Suggested keys:

```text
studyflow_courses
studyflow_sources
studyflow_tasks
studyflow_chat_threads
studyflow_chat_messages
studyflow_quiz_results
studyflow_flashcards
```

Rule:

- On app start, load from localStorage.
- If empty, seed mock data.
- On create/update/delete, update localStorage.

---

# 17. Error, Loading, Empty States

## 17.1 Error messages

Examples:

```text
Không thể tải danh sách môn học.
Không thể tạo lịch học.
Không thể gửi câu hỏi cho AI.
Không thể xử lý tài liệu này.
```

## 17.2 Loading states

Need loading states for:

- Dashboard load
- Course list load
- Source upload/parse
- Chat response
- Quiz generation
- Flashcard generation
- Schedule generation/reschedule

## 17.3 Empty states

Need empty states for:

- No courses
- No sources
- No chat history
- No tasks today
- No schedule events
- No flashcards
- No quiz results

---

# 18. Codex Development Order

## Phase 1 — UI + Routing

1. Setup routes.
2. Implement shared layout/components.
3. Render Dashboard.
4. Render Courses.
5. Render Schedule.
6. Render Study Workspace.
7. Render Onboarding Step 1.

## Phase 2 — State + Mock Functionality

1. Add mock store.
2. Add create course.
3. Add filters/search/sort.
4. Add calendar event popover.
5. Add create task modal.
6. Add workspace tab switching.
7. Add fake chat response.

## Phase 3 — Practice Features

1. Quiz generation mock.
2. Quiz session.
3. Results page.
4. Flashcard session.
5. Chat context from quiz/flashcard.

## Phase 4 — Backend Integration

1. Replace mock service with API calls.
2. Add database.
3. Add upload.
4. Add parsing.
5. Add AI/RAG.
6. Add real scheduling/rescheduling.

---

# 19. Final Acceptance Criteria

Website is functional MVP when:

- User can create a course.
- Created course appears on Courses page.
- Created course appears in Dashboard.
- User can view schedule.
- User can create a task in calendar.
- User can click task and open detail popover.
- User can open Study Workspace for a course.
- User can switch between Sources and Chat History.
- User can send a chat message and receive an assistant response.
- Assistant response shows citations/actions.
- User can generate/open a mock quiz.
- User can finish quiz and see results.
- User can click `Hỏi AI giải thích` and open chatbot with context.
- User can open flashcard session and rate cards.
- Reschedule modal can open and apply mock changes.
- App works on desktop/laptop browser.
- No mobile app/mobile-first requirements are implemented.
