# StudyFlow AI — UI Layout Spec for Codex

> File này dùng cho **Codex** để code frontend UI prototype cho StudyFlow AI.  
> Scope: mô tả bố cục các page chính: **Dashboard, Môn học, Lịch học, Chatbot / Study Workspace, Onboarding tạo môn học**.  
> Target: **responsive web app**, tập trung cho desktop/laptop browser, ưu tiên viewport `1440×810` hoặc `1600×900`.  
> Chưa cần backend thật; dùng mock data và fake interaction để demo.  
> **Không làm mobile app, không thiết kế mobile-first, không cần tối ưu giao diện điện thoại.**

---

## 0. Product Context

**StudyFlow AI** là web app trợ lý học tập cho sinh viên. Người dùng tạo môn học, thêm tài liệu, đặt mục tiêu điểm số và lịch trống. Ứng dụng hỗ trợ lập lịch học, tạo quiz, flashcard, chatbot hỏi đáp theo tài liệu, theo dõi mastery theo topic và lập lại lịch khi người dùng bỏ lỡ nhiệm vụ.

Các page cần code:

1. Dashboard
2. Môn học
3. Lịch học
4. Chatbot / Study Workspace
5. Onboarding tạo môn học

Không cần code trong scope này:

- Login/auth thật
- Backend upload thật
- AI thật
- Database thật
- Calendar drag-and-drop phức tạp
- Mobile app hoặc mobile-first layout

---

## 1. Global Design Rules

### 1.1 Responsive Web Scope

Chỉ tập trung làm **web app chạy trên browser**. Không làm mobile app và không cần tối ưu giao diện điện thoại.

Ưu tiên thiết kế cho desktop/laptop:

```text
Primary viewport: 1440×810
Large desktop: 1600×900
Compact laptop: 1280×720 hoặc 1366×768
Minimum supported web width: 1024px
```

Yêu cầu:

- Layout phải responsive trong phạm vi web desktop/laptop.
- Component đủ lớn để đọc rõ ở 1280px trở lên.
- Không để page quá trống ở 1440px hoặc 1600px.
- Không tạo landing page dài; các page chính nên hiển thị phần quan trọng nhất trong một viewport.
- Không thiết kế mobile-first.
- Không cần hamburger mobile menu.
- Không cần bottom navigation.
- Không cần layout điện thoại 1 cột.
- Nếu viewport nhỏ hơn 1024px, có thể hiển thị warning hoặc cho phép horizontal scroll ở các page phức tạp như Calendar và Workspace.

### 1.2 Responsive Breakpoints cho Web

Dùng các breakpoint web sau:

| Breakpoint | Width | Cách xử lý |
|---|---:|---|
| Compact laptop | 1024–1279px | Giảm gap/padding, card nhỏ hơn, giữ layout chính |
| Standard desktop | 1280–1439px | Layout mặc định |
| Wide desktop | 1440–1599px | Tối ưu cho 16:9, spacing thoáng |
| Large desktop | >=1600px | Giữ max-width, không kéo component quá rộng |

Quy tắc:

- Dùng `max-width` cho PageContainer để tránh nội dung bị kéo quá rộng.
- Dùng CSS Grid/Flex với `minmax()` thay vì width cứng tuyệt đối.
- Các grid card nên dùng `auto-fit` hoặc `auto-fill` với minimum card width.
- Với layout 3 cột như Study Workspace, giữ 3 cột trên desktop; không collapse xuống mobile layout.
- Với Calendar, giữ week grid; nếu hẹp thì cho phép scroll ngang trong vùng calendar.

### 1.3 Page Container

Gợi ý:

```css
.page-container {
  width: min(100% - 48px, 1240px);
  margin: 0 auto;
}

@media (min-width: 1600px) {
  .page-container {
    width: min(100% - 64px, 1360px);
  }
}

@media (max-width: 1279px) {
  .page-container {
    width: min(100% - 32px, 1180px);
  }
}
```

### 1.4 Visual Style

Phong cách:

- Clean
- Modern
- Student-friendly
- Card-based
- Soft green accent
- Không quá giống admin dashboard khô cứng

Design tokens gợi ý:

```css
:root {
  --brand-green: #7ED957;
  --brand-green-soft: #ECF8E8;
  --brand-dark: #163300;

  --surface-app: #F6FAF2;
  --surface-card: #FFFFFF;
  --surface-muted: #F3F4F6;

  --text-primary: #1C1C1C;
  --text-secondary: #6B7280;
  --text-muted: #9CA3AF;

  --border-default: #E5E7EB;

  --status-success: #22C55E;
  --status-warning: #FACC15;
  --status-error: #EF4444;

  --radius-card: 16px;
  --radius-button: 999px;
  --radius-input: 12px;

  --page-max-width: 1240px;
  --page-padding-x: 32px;
  --page-padding-y: 24px;
}
```

### 1.5 Typography

Dùng font sans-serif hiện đại, ví dụ Inter hoặc system-ui.

| Thành phần | Size |
|---|---:|
| Page title | 24–30px |
| Section title | 18–22px |
| Card title | 15–18px |
| Body | 14–16px |
| Caption | 12–13px |
| Button | 14–15px |

### 1.6 Shared Components

Nên tạo các component dùng chung:

```text
TopNav
PageContainer
HeaderBar
Card
Button
Badge
ProgressBar
ProgressRing
SearchInput
Tabs
PillButton
IconButton
Modal
```

---

## 2. Web Responsive Implementation Rules

### 2.1 Không làm mobile

Codex không cần tạo mobile-specific UI. Không cần:

- Bottom nav.
- Mobile hamburger menu.
- Full mobile card stacking.
- Touch-only interactions.
- Native mobile app layout.
- Mobile onboarding riêng.
- Mobile calendar riêng.

Tuy nhiên, UI vẫn phải responsive trong browser khi thay đổi width trên desktop/laptop.

### 2.2 Layout behavior theo page

| Page | 1440px / 1600px | 1280px / 1366px | 1024px |
|---|---|---|---|
| Dashboard | 2 cột: main + stats | 2 cột, giảm gap | 2 cột hẹp hoặc stats panel nhỏ hơn |
| Môn học | Gallery 4–5 cards/hàng | 3–4 cards/hàng | 3 cards/hàng |
| Lịch học | Google Calendar week view + left panel | Giữ week view, giảm left panel | Calendar grid scroll ngang nếu cần |
| Chatbot | 3 cột NotebookLM | 3 cột, giảm width panel | 3 cột min-width + horizontal scroll nếu cần |
| Onboarding | 2 cột form + preview | 2 cột, preview nhỏ hơn | 2 cột hẹp hoặc preview card dưới nếu thật sự thiếu chỗ |

### 2.3 CSS layout gợi ý

Dùng CSS Grid/Flex thay vì pixel cứng.

Dashboard:

```css
.dashboard-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 24px;
}

@media (max-width: 1279px) {
  .dashboard-layout {
    grid-template-columns: minmax(0, 1fr) 280px;
    gap: 16px;
  }
}
```

Courses gallery:

```css
.course-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 16px;
}
```

Study Workspace:

```css
.workspace-layout {
  display: grid;
  grid-template-columns: 320px minmax(520px, 1fr) 320px;
  min-width: 1120px;
}
```

Calendar:

```css
.calendar-page {
  display: grid;
  grid-template-columns: 260px minmax(760px, 1fr);
}

.calendar-grid-wrapper {
  overflow-x: auto;
}
```

### 2.4 Typography responsive

Không giảm font quá nhỏ.

- Body tối thiểu 14px.
- Caption tối thiểu 12px.
- Button tối thiểu 14px.
- Không dùng font 10px cho metadata quan trọng.

### 2.5 Spacing responsive

- Desktop wide: padding page 32px.
- Compact laptop: padding page 16–24px.
- Gap card: 16–24px.
- Không để gap lớn hơn 32px trong layout chính.


---

## 3. Suggested Routes

```text
/                       -> Dashboard
/dashboard              -> Dashboard
/courses                -> Môn học
/courses/new            -> Onboarding tạo môn học
/schedule               -> Lịch học
/study/:courseId        -> Chatbot / Study Workspace
```

Nếu chưa cần routing, có thể render bằng state/tab để demo.

---

## 4. Mock Data

Dùng mock data cố định để UI có nội dung thật.

```js
const user = { name: "Hải Dương" };

const courses = [
  {
    id: "linear-algebra",
    name: "Đại số tuyến tính",
    mode: "Ôn thi tăng tốc",
    examLabel: "12 ngày nữa",
    sourceCount: 42,
    mastery: 70,
    status: "Cần chú ý",
    priority: "Cao",
    updatedAt: "14 thg 6, 2026"
  },
  {
    id: "calculus",
    name: "Giải tích",
    mode: "Học kỳ liên tục",
    examLabel: "28 ngày nữa",
    sourceCount: 28,
    mastery: 64,
    status: "Đúng tiến độ",
    priority: "Trung bình",
    updatedAt: "13 thg 6, 2026"
  },
  {
    id: "advanced-algorithms",
    name: "Các thuật toán nâng cao",
    mode: "Học kỳ liên tục",
    examLabel: "Chưa đặt ngày thi",
    sourceCount: 19,
    mastery: 45,
    status: "Chậm",
    priority: "Cao",
    updatedAt: "12 thg 6, 2026"
  },
  {
    id: "academic-english",
    name: "Tiếng Anh học thuật",
    mode: "Học kỳ liên tục",
    examLabel: "Đúng tiến độ",
    sourceCount: 16,
    mastery: 82,
    status: "Đúng tiến độ",
    priority: "Thấp",
    updatedAt: "11 thg 6, 2026"
  },
  {
    id: "statistics",
    name: "Xác suất thống kê",
    mode: "Ôn thi tăng tốc",
    examLabel: "Sắp thi",
    sourceCount: 21,
    mastery: 58,
    status: "Cần chú ý",
    priority: "Cao",
    updatedAt: "10 thg 6, 2026"
  }
];

const todayTasks = [
  {
    id: "task-1",
    type: "Quiz",
    title: "Không gian vector",
    courseName: "Đại số tuyến tính",
    duration: "20 phút",
    reason: "Topic yếu và còn 12 ngày trước kỳ thi"
  },
  {
    id: "task-2",
    type: "Flashcard",
    title: "Tích phân từng phần",
    courseName: "Giải tích",
    duration: "18 thẻ · 15 phút",
    reason: "Flashcards đến hạn hôm nay"
  },
  {
    id: "task-3",
    type: "Hỏi AI",
    title: "Dynamic Programming",
    courseName: "Các thuật toán nâng cao",
    duration: "10 phút",
    reason: "Bạn đã sai 3 câu gần đây"
  }
];

const weakTopics = [
  { name: "Không gian vector", courseName: "Đại số tuyến tính", mastery: 42, action: "Luyện" },
  { name: "Tích phân từng phần", courseName: "Giải tích", mastery: 48, action: "Ôn" },
  { name: "Dynamic Programming", courseName: "Các thuật toán nâng cao", mastery: 51, action: "Hỏi AI" }
];

const sources = [
  { id: "src-1", filename: "lecture_01_vector_space.pdf", type: "PDF", status: "Đã xử lý", topicCount: 12, selected: true },
  { id: "src-2", filename: "old_exam_2024.pdf", type: "Đề thi", status: "Đã xử lý", topicCount: 8, selected: true },
  { id: "src-3", filename: "note_week_2.docx", type: "DOCX", status: "Đã xử lý", topicCount: 5, selected: false }
];

const chatHistory = [
  { id: "chat-1", title: "Ôn Không gian vector", courseName: "Đại số tuyến tính", time: "10 phút trước" },
  { id: "chat-2", title: "Giải thích câu sai quiz", courseName: "Đại số tuyến tính", time: "35 phút trước", badge: "Từ Quiz Result" },
  { id: "chat-3", title: "Tích phân từng phần", courseName: "Giải tích", time: "Thứ 3" },
  { id: "chat-4", title: "Dynamic Programming", courseName: "Các thuật toán nâng cao", time: "Thứ 2" }
];

const scheduleEvents = [
  {
    id: "event-1",
    title: "Quiz: Không gian vector",
    courseName: "Đại số tuyến tính",
    type: "Quiz",
    day: "T2",
    start: "18:00",
    end: "18:20",
    color: "green",
    reason: "Topic yếu, mastery 42%",
    source: "lecture_01_vector_space.pdf"
  },
  {
    id: "event-2",
    title: "Flashcard: Tích phân từng phần",
    courseName: "Giải tích",
    type: "Flashcard",
    day: "T3",
    start: "19:00",
    end: "19:15",
    color: "blue"
  },
  {
    id: "event-3",
    title: "Ôn tập: Dynamic Programming",
    courseName: "Các thuật toán nâng cao",
    type: "Ôn tập",
    day: "T5",
    start: "19:30",
    end: "20:00",
    color: "purple"
  },
  {
    id: "event-4",
    title: "Mock test: Đại số tuyến tính",
    courseName: "Đại số tuyến tính",
    type: "Mock test",
    day: "T4",
    start: "20:00",
    end: "21:00",
    color: "pink"
  }
];
```


---

# 5. Page: Dashboard

## 10.1 Mục tiêu

Dashboard là trang đầu tiên sau khi vào app. Nó cần trả lời nhanh:

- Hôm nay cần học gì?
- Task nào quan trọng nhất?
- Môn nào cần chú ý?
- Topic nào yếu?
- Deadline gần nhất là gì?
- Tuần này học được bao nhiêu?

## 10.2 Layout

Dashboard dùng top navigation ngang, không sidebar.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TopNav                                                                       │
│ [StudyFlow] [Trang chủ] [Môn học] [Lịch học] [Chatbot] [Search] [Avatar]     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ PageContainer                                                                │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────┐ ┌───────────┐ │
│ │ Main Column                                                │ │ Stats     │ │
│ │ Header                                                     │ │ Panel     │ │
│ │ Focus Card                                                 │ │           │ │
│ │ Today Tasks                                                │ │           │ │
│ │ Course Progress + Weak Topics                              │ │           │ │
│ │ Due Reviews Strip                                          │ │           │ │
│ └────────────────────────────────────────────────────────────┘ └───────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

Tỉ lệ:

- Main column: 68–72%
- Right stats panel: 28–32%
- Gap: 24px

## 10.3 TopNav

```text
[Logo] StudyFlow
[Trang chủ] [Môn học] [Lịch học] [Chatbot]
[Search input] [Notification icon] [Avatar]
```

Active page: `Trang chủ`.

## 10.4 Dashboard Header

```text
Chào mừng, Hải Dương!
Hôm nay bạn có 3 nhiệm vụ, tổng cộng 45 phút.
```

Bên phải header:

```text
[Học kỳ hiện tại] [Tuần này]
```

## 10.5 Focus Card

```text
Quiz: Không gian vector
Đại số tuyến tính · 20 phút
Ưu tiên hôm nay
Lý do: Đây là topic yếu và còn 12 ngày trước kỳ thi.
[Bắt đầu học] [Xem lý do]
```

Yêu cầu:

- Card lớn nhất trong main column.
- Có badge `Ưu tiên hôm nay`.
- CTA `Bắt đầu học` nổi bật.
- Có thể thêm progress bar nhỏ cho topic mastery.

## 10.6 Today Task Cards

Hiển thị 3 cards ngang.

```text
Quiz
Không gian vector
Đại số tuyến tính
20 phút
[Làm ngay]
```

```text
Flashcard
Tích phân từng phần
Giải tích
18 thẻ · 15 phút
[Ôn ngay]
```

```text
Hỏi AI
Dynamic Programming
Thuật toán nâng cao
10 phút
[Mở chatbot]
```

## 10.7 Course Progress + Weak Topics

Hai card ngang bên dưới Today Tasks.

### Course Progress Card

```text
Các môn học

Đại số tuyến tính        Cần chú ý      70%   [progress bar]
Giải tích                Đúng tiến độ   64%   [progress bar]
Các thuật toán nâng cao  Chậm           45%   [progress bar]
```

### Weak Topics Card

```text
Chủ đề cần chú ý

Không gian vector        Mastery 42%    [Luyện]
Tích phân từng phần      Mastery 48%    [Ôn]
Dynamic Programming      Mastery 51%    [Hỏi AI]
```

## 10.8 Due Reviews Strip

```text
Due Reviews
18 flashcards đến hạn hôm nay · 3 topic cần ôn lại
[Ôn flashcards] [Xem lịch]
```

## 10.9 Right Stats Panel

```text
Thống kê học tập

75%
Tiến độ tuần này

Hôm nay: 2/3 nhiệm vụ
Tuần này: 165 phút
Streak: 4 ngày

Deadline gần nhất
Đại số tuyến tính · 12 ngày nữa

Lịch gần nhất
19:00 · Quiz Không gian vector

Tiến độ môn
Đại số tuyến tính   70%
Giải tích           64%
Thuật toán NC       45%
```

Yêu cầu:

- Dùng progress ring/circle cho 75%.
- Dùng mini progress bars cho tiến độ môn.
- Không thêm chart phức tạp.

## 10.10 Dashboard Acceptance

- Không có sidebar.
- Có top nav ngang.
- Có focus card.
- Có 3 task cards.
- Có course progress card.
- Có weak topics card.
- Có due reviews strip.
- Có right stats panel.
- Không để dashboard bị trống.

---

# 6. Page: Môn học

## 10.1 Mục tiêu

Trang `Môn học` giống gallery page của NotebookLM. Mỗi môn học là một study notebook/workspace.

## 10.2 Layout

Không dùng sidebar.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Header                                                                       │
│ [Logo] StudyFlow                                      [Cài đặt] [Apps] [Avatar] │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Main Content Container                                                       │
│                                                                              │
│ Filter Tabs                                      Toolbar bên phải            │
│ [Tất cả] [Môn học của tôi] [Môn nổi bật] [Được chia sẻ với tôi]              │
│                                      [Search] [Grid/List] [Gần đây nhất] [+ Tạo mới] │
│                                                                              │
│ Môn học nổi bật                                                              │
│ [Featured Course Card] [Featured Course Card] [Featured Course Card]         │
│ [Featured Course Card] [Featured Course Card]                       [Xem tất cả] │
│                                                                              │
│ Môn học gần đây                                                              │
│ [Create New Card] [Course Card] [Course Card] [Course Card] [Course Card]    │
│ [Course Card]     [Course Card] [Course Card]                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 10.3 Header

Bên trái:

```text
[Logo] StudyFlow
```

Bên phải:

```text
[Cài đặt] [Apps/Grid Icon] [Avatar]
```

Không cần top nav nhiều tab ở page này để giống NotebookLM.

## 10.4 Filter Tabs

```text
[Tất cả] [Môn học của tôi] [Môn học nổi bật] [Được chia sẻ với tôi]
```

Active tab dạng pill nổi bật.

## 10.5 Toolbar

```text
[Search icon] [Select/check icon] [Grid icon] [List icon] [Gần đây nhất ▼] [+ Tạo mới]
```

`+ Tạo mới` là primary button.

## 10.6 Section: Môn học nổi bật

Hiển thị 4–5 cards ngang.

Featured card:

```text
[Background gradient/pattern]
[Icon] Đại số tuyến tính
Ôn thi tăng tốc
12 ngày nữa · 42 nguồn
Mastery 70%
[small progress bar]
```

Featured courses:

```text
Đại số tuyến tính — Ôn thi tăng tốc · 12 ngày nữa · 42 nguồn · Mastery 70%
Giải tích — Học kỳ liên tục · 28 nguồn · Mastery 64%
Các thuật toán nâng cao — Cần chú ý · 19 nguồn · Mastery 45%
Tiếng Anh học thuật — Đúng tiến độ · 16 nguồn · Mastery 82%
Xác suất thống kê — Sắp thi · 21 nguồn · Mastery 58%
```

## 10.7 Section: Môn học gần đây

Card đầu tiên:

```text
+
Tạo môn học mới
```

Course card:

```text
[Subject icon]           [⋮]

Đại số tuyến tính

14 thg 6, 2026 · 42 nguồn
Mastery 70%

[Progress bar]
```

Recent courses:

```text
Tạo môn học mới
Đại số tuyến tính — 14 thg 6, 2026 · 42 nguồn
Giải tích — 13 thg 6, 2026 · 28 nguồn
Các thuật toán nâng cao — 12 thg 6, 2026 · 19 nguồn
Trắc nghiệm Tổng hợp Kiến thức Web — 12 thg 1, 2026 · 2 nguồn
Digital Image Processing Final — 12 thg 1, 2026 · 2 nguồn
```

## 10.8 Card Size

Cho canvas 1440×810:

```text
Featured card width: 210–250px
Featured card height: 150–170px

Recent card width: 210–250px
Recent card height: 155–185px
```

## 10.9 Môn học Acceptance

- Giống gallery page của NotebookLM.
- Không có sidebar.
- Có header với logo trái, settings/apps/avatar phải.
- Có filter tabs.
- Có toolbar.
- Có section `Môn học nổi bật`.
- Có section `Môn học gần đây`.
- Card đầu tiên là `Tạo môn học mới`.
- Card đủ lớn, dễ đọc.


---

# 7. Page: Lịch học

## 10.1 Mục tiêu

Trang `Lịch học` giống Google Calendar. Người dùng xem lịch học theo tuần, ngày, tháng hoặc agenda.

## 10.2 Layout

Page này có left calendar utility panel giống Google Calendar. Đây không phải sidebar điều hướng app.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Top Header                                                                   │
│ [Calendar Icon] StudyFlow Calendar                    [Search] [Help] [Settings] [Avatar] │
├──────────────────────────────────────────────────────────────────────────────┤
│ Calendar Toolbar                                                             │
│ [Hôm nay] [<] [>]  15–21 tháng 6, 2026         [Ngày] [Tuần] [Tháng] [Lịch biểu] [+] │
├───────────────────────┬──────────────────────────────────────────────────────┤
│ Left Calendar Panel   │ Main Calendar Grid                                   │
│                       │                                                      │
│ [+ Tạo nhiệm vụ học]  │ Week grid                                            │
│ Mini calendar         │ Event blocks                                         │
│ Lịch của tôi          │                                                      │
│ Loại nhiệm vụ         │                                                      │
│ Cần chú ý             │                                                      │
└───────────────────────┴──────────────────────────────────────────────────────┘
```

## 10.3 Header

```text
[Calendar icon] StudyFlow Calendar
[Search] [Help] [Settings] [Apps/Grid] [Avatar]
```

## 10.4 Toolbar

```text
[Hôm nay] [<] [>]  15–21 tháng 6, 2026      [Ngày] [Tuần] [Tháng] [Lịch biểu] [+ Tạo]
```

View mặc định: `Tuần`.

## 10.5 Left Calendar Panel

Width: 240–280px.

```text
[+ Tạo nhiệm vụ học]

Tháng 6, 2026
Mini calendar

Lịch của tôi
☑ Đại số tuyến tính
☑ Giải tích
☑ Các thuật toán nâng cao

Loại nhiệm vụ
☑ Quiz
☑ Flashcard
☑ Ôn tập
☑ Hỏi AI
☑ Mock test

Cần chú ý
2 nhiệm vụ bị trễ
[Lập lại lịch]
```

## 10.6 Main Calendar Grid

Week view:

```text
GMT+7 | T2 15/6 | T3 16/6 | T4 17/6 | T5 18/6 | T6 19/6 | T7 20/6 | CN 21/6
07:00
08:00
09:00
...
18:00  Quiz: Không gian vector
19:00            Flashcard: Tích phân
20:00                      Mock test Đại số
21:00
```

Yêu cầu:

- Cột giờ bên trái.
- 7 cột ngày.
- Header ngày rõ.
- Hôm nay highlight nhẹ.
- Grid line nhẹ.
- Event block đủ lớn để đọc.
- Giờ 18:00–22:00 nên dễ nhìn.

## 10.7 Event Block

Ví dụ:

```text
Quiz: Không gian vector
18:00 · 20 phút
Đại số tuyến tính
```

Màu event:

| Type | Màu |
|---|---|
| Quiz | Xanh lá |
| Flashcard | Xanh dương nhạt |
| Ôn tập | Tím nhạt |
| Hỏi AI | Cam nhạt |
| Mock test | Hồng/đỏ nhạt |
| Missed | Vàng cảnh báo |

## 10.8 Event Detail Popover

Khi click event:

```text
Quiz: Không gian vector      [⋮]
Đại số tuyến tính

Thời gian: T2, 18:00–18:20
Loại: Quiz
Lý do: Topic yếu, mastery 42%
Source: lecture_01_vector_space.pdf

[Bắt đầu học] [Dời lịch] [Xem môn]
```

## 10.9 Create Task Modal

Khi bấm `+ Tạo nhiệm vụ học`:

```text
Tạo nhiệm vụ học

Tiêu đề
[Quiz: Không gian vector]

Môn học
[Đại số tuyến tính ▼]

Loại nhiệm vụ
[Quiz] [Flashcard] [Ôn tập] [Hỏi AI] [Mock test]

Thời gian
[T2, 15/6] [18:00] - [18:20]

Lý do / ghi chú
[Topic yếu, cần ôn lại trước kỳ thi]

[Hủy] [Lưu nhiệm vụ]
```

## 10.10 Lịch học Acceptance

- Giống Google Calendar.
- Có header.
- Có toolbar.
- Có left utility panel.
- Có week calendar grid.
- Có event blocks màu.
- Click event mở popover.
- Có button `+ Tạo nhiệm vụ học`.
- Có `Lập lại lịch` khi có task trễ.

---

# 8. Page: Chatbot / Study Workspace

## 10.1 Mục tiêu

Study Workspace giống NotebookLM. Đây là nơi người dùng làm việc với tài liệu, hỏi AI, xem lịch sử chat và tạo output học tập.

## 10.2 Layout

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Workspace Top Bar                                                            │
│ [Icon] Sổ ghi chú Đại số tuyến tính      [+ Tạo ghi chú] [Số liệu phân tích] [Chia sẻ] [Cài đặt] [Avatar] │
├───────────────────────┬──────────────────────────────────┬───────────────────┤
│ Left Sidebar          │ Conversation                     │ Studio            │
│ [Nguồn] [Lịch sử chat]│                                  │                   │
└───────────────────────┴──────────────────────────────────┴───────────────────┘
```

Tỉ lệ:

```text
Left Sidebar: 25%
Conversation: 50%
Studio: 25%
```

Pixel gợi ý 1440×810:

```text
Left Sidebar: 330–360px
Conversation: 680–760px
Studio: 330–360px
```

## 10.3 Workspace Top Bar

Bên trái:

```text
[Icon] Sổ ghi chú Đại số tuyến tính
```

Bên phải, căn phải:

```text
[+ Tạo ghi chú] [Số liệu phân tích] [Chia sẻ] [Cài đặt] [Avatar]
```

Yêu cầu:

- Buttons bên phải phải căn phải.
- Tên workspace bên trái.
- Top bar giống NotebookLM, không giống dashboard nav.

## 10.4 Left Sidebar Tabs

Left Sidebar có 2 tab:

```text
[Nguồn] [Lịch sử chat]
```

Tab active có nền xanh nhạt hoặc border active.

### Tab Nguồn

```text
[+ Thêm nguồn]

[Tìm nguồn...]

Các nguồn đã thêm:
☑ lecture_01_vector_space.pdf
PDF · 12 topics

☑ old_exam_2024.pdf
Đề thi · 8 topics

☐ note_week_2.docx
DOCX · 5 topics
```

Source item có:

- Checkbox.
- Filename.
- Type.
- Topic count.
- Menu 3 chấm.
- Status nếu cần.

### Tab Lịch sử chat

Khi active, thay toàn bộ nội dung nguồn bằng chat history.

```text
[Tìm cuộc trò chuyện...]

Hôm nay
Ôn Không gian vector
Đại số tuyến tính · 10 phút trước

Giải thích câu sai quiz
Đại số tuyến tính · Từ Quiz Result

Tuần này
Tích phân từng phần
Giải tích · Thứ 3

Dynamic Programming
Thuật toán nâng cao · Thứ 2
```

Click chat history item sẽ load conversation vào cột giữa.

## 10.5 Conversation Panel

### Empty State

```text
Hãy bắt đầu không gian học của bạn...

Thêm slide, PDF, đề thi hoặc ghi chú để StudyFlow tạo quiz,
flashcard, lịch ôn và trả lời câu hỏi dựa trên nguồn.

Bạn muốn StudyFlow giúp gì hôm nay?

[Hỏi về tài liệu]
[Tạo quiz từ nguồn]
[Tạo flashcards]
```

Chat input ở đáy:

```text
Đặt câu hỏi hoặc tạo nội dung...
```

Dòng nhỏ:

```text
Đang dùng 3 nguồn
```

### Chat Message

User:

```text
Giải thích giúp tôi không gian vector là gì.
```

Assistant:

```text
Trả lời ngắn
Không gian vector là một tập hợp các vector thỏa mãn các quy tắc về cộng vector và nhân vô hướng.

Giải thích chi tiết
Một tập vector được xem là không gian vector khi nó đóng với phép cộng, đóng với phép nhân vô hướng và thỏa mãn các tiên đề vector.

Nguồn
[1] lecture_01_vector_space.pdf · trang 12
[2] note_week_2.docx · đoạn 4

Hành động tiếp theo
[Tạo 5 flashcards] [Ra 3 câu quiz] [Thêm vào lịch ôn] [Giải thích dễ hơn]
```

### Context Card từ quiz

```text
Context từ Quiz

Môn: Đại số tuyến tính
Topic: Không gian vector
Câu hỏi: Điều kiện để một tập vector là không gian con là gì?
Bạn đã chọn: Chỉ cần đóng với phép cộng
Đáp án đúng: Cần chứa vector không, đóng với cộng và nhân vô hướng
Source: lecture_01_vector_space.pdf · trang 12

[Ẩn context]
```

## 10.6 Studio Panel

Bố cục card 2 cột nhỏ.

```text
Studio

[Banner nhỏ: Hãy dùng thử các chế độ tạo nội dung]

[Tạo quiz] [Tạo flashcard]
[Study guide] [Bản đồ tư duy]
[Checklist ôn thi] [Mock test]
[Báo cáo học tập] [Tóm tắt topic yếu]

Đầu ra của Studio sẽ được lưu ở đây.
[Thêm ghi chú]
```

## 10.7 Chatbot Acceptance

- Giống NotebookLM.
- Có top bar với tên workspace bên trái.
- Buttons bên phải căn phải.
- Có 3 cột.
- Left sidebar có 2 tab: Nguồn và Lịch sử chat.
- Tab Nguồn hiển thị source.
- Tab Lịch sử chat hiển thị chat history.
- Conversation panel có empty state và chat input.
- Assistant response có citations và action buttons.
- Studio có action cards.


---

# 9. Page: Onboarding tạo môn học

## 10.1 Mục tiêu

Onboarding là full-page screen đầu tiên để tạo môn học mới. Scope hiện tại chỉ cần code screen đầu tiên: `Thông tin môn`.

Không cần code 4 screen đầy đủ, nhưng stepper vẫn hiển thị 4 bước.

## 10.2 Layout

Không popup. Không sidebar.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Top Bar                                                                      │
│ [Logo] StudyFlow                                      [Cần trợ giúp?] [Avatar] │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ PageContainer                                                                │
│                                                                              │
│ Tạo môn học mới                                                              │
│ Thiết lập môn học để StudyFlow tạo lịch học, quiz, flashcard...              │
│                                                                              │
│ Stepper: 1 Thông tin môn → 2 Mục tiêu & lịch → 3 Tài liệu → 4 Xác nhận       │
│                                                                              │
│ ┌──────────────────────────────────────────────┐ ┌─────────────────────────┐ │
│ │ Form Card                                    │ │ Preview Card             │ │
│ │ Bạn đang học môn gì?                         │ │ StudyFlow sẽ dùng...     │ │
│ │ Tên môn học                                  │ │ Summary + benefits       │ │
│ │ Chế độ học                                   │ │                         │ │
│ │ Mức độ ưu tiên                               │ │                         │ │
│ │ [Hủy] [Tiếp tục]                             │ │                         │ │
│ └──────────────────────────────────────────────┘ └─────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 10.3 Top Bar

```text
[Logo icon] StudyFlow
[Cần trợ giúp?] [Avatar]
```

## 10.4 Page Header

Title:

```text
Tạo môn học mới
```

Subtitle:

```text
Thiết lập môn học để StudyFlow tạo lịch học, quiz, flashcard và chatbot theo tài liệu của bạn.
```

## 10.5 Stepper

```text
1. Thông tin môn
2. Mục tiêu & lịch
3. Tài liệu
4. Xác nhận
```

Step 1 active xanh lá. Các step còn lại xám.

## 10.6 Form Card

Title:

```text
Bạn đang học môn gì?
```

Subtitle:

```text
Nhập thông tin cơ bản để StudyFlow hiểu môn học và chọn cách hỗ trợ phù hợp.
```

### Tên môn học

```text
Tên môn học
[Đại số tuyến tính]
```

### Chế độ học

2 selection cards đặt cạnh nhau.

Card 1:

```text
Học kỳ liên tục
Theo dõi tiến độ, ôn tập đều trong nhiều tuần.
Phù hợp khi bạn đang học môn này trên lớp.
```

Card 2 selected:

```text
Ôn thi tăng tốc
Ưu tiên phần quan trọng khi ngày thi đang đến gần.
Phù hợp khi bạn cần ôn trong thời gian ngắn.
```

Card selected:

- Border xanh lá.
- Nền xanh nhạt.
- Có check icon.

### Mức độ ưu tiên

```text
[Thấp] [Trung bình] [Cao]
```

Pill `Cao` selected.

## 10.7 Preview Card

Title:

```text
StudyFlow sẽ dùng thông tin này để
```

List:

```text
- Ưu tiên lịch học cho môn quan trọng
- Điều chỉnh độ khó quiz
- Theo dõi mastery theo từng topic
- Gợi ý nhiệm vụ học phù hợp
```

Mini summary:

```text
Môn học
Đại số tuyến tính

Chế độ
Ôn thi tăng tốc

Ưu tiên
Cao
```

## 10.8 Footer Actions

```text
[Hủy] [Tiếp tục]
```

`Tiếp tục` là primary CTA.

## 10.9 Onboarding Acceptance

- Full-page screen, không popup.
- Không sidebar.
- Có top bar.
- Có page title.
- Có stepper 4 bước với step 1 active.
- Có form card bên trái.
- Có preview card bên phải.
- Có input tên môn.
- Có selection cards cho chế độ học.
- Có pill priority.
- Có buttons Hủy và Tiếp tục.

---

# 9. Implementation Notes for Codex

## 10.1 Scope

Codex chỉ cần implement UI prototype.

Không cần:

- Backend thật
- Upload thật
- AI thật
- Database thật
- Auth thật
- Drag-and-drop calendar thật

## 10.2 Fake interactions nên có

Nên implement:

- Click tab trong Chatbot Left Sidebar để đổi giữa `Nguồn` và `Lịch sử chat`.
- Click filter tab trên Môn học đổi active state.
- Click event trong Lịch học mở popover.
- Click `+ Tạo nhiệm vụ học` mở modal.
- Click selection card trong Onboarding đổi selected state.
- Click priority pill đổi selected state.

## 10.3 Suggested Component Tree

```text
App
├── DashboardPage
├── CoursesPage
├── SchedulePage
├── StudyWorkspacePage
└── OnboardingCoursePage

components/
├── layout/
│   ├── TopNav
│   ├── PageContainer
│   └── HeaderBar
├── common/
│   ├── Card
│   ├── Button
│   ├── Badge
│   ├── ProgressBar
│   ├── ProgressRing
│   ├── Tabs
│   └── Modal
├── dashboard/
│   ├── FocusCard
│   ├── TaskCard
│   ├── CourseProgressCard
│   ├── WeakTopicsCard
│   ├── DueReviewsStrip
│   └── StatsPanel
├── courses/
│   ├── CoursesHeader
│   ├── FilterTabs
│   ├── CoursesToolbar
│   ├── FeaturedCourseCard
│   └── RecentCourseCard
├── schedule/
│   ├── CalendarHeader
│   ├── CalendarToolbar
│   ├── CalendarLeftPanel
│   ├── WeekGrid
│   ├── CalendarEventBlock
│   ├── EventPopover
│   └── CreateTaskModal
├── workspace/
│   ├── WorkspaceTopBar
│   ├── WorkspaceLeftSidebar
│   ├── SourcesTab
│   ├── ChatHistoryTab
│   ├── ConversationPanel
│   ├── ChatComposer
│   └── StudioPanel
└── onboarding/
    ├── OnboardingStepper
    ├── CourseInfoForm
    └── OnboardingPreviewCard
```

## 10.4 Final Acceptance

- UI pages đúng layout mô tả.
- Responsive trong phạm vi web desktop/laptop.
- Desktop 16:9 đẹp ở 1440×810 và 1600×900.
- Vẫn dùng được ở compact laptop 1280×720 hoặc 1366×768.
- Không làm mobile app hoặc mobile-first layout.
- Không có sidebar ở Dashboard, Môn học, Onboarding.
- Schedule được phép có left utility panel giống Google Calendar.
- Chatbot có left sidebar tabs, nhưng đây là workspace panel, không phải app navigation.
- Môn học giống NotebookLM gallery.
- Lịch học giống Google Calendar.
- Chatbot giống NotebookLM.
- Onboarding là full-page screen step 1.
