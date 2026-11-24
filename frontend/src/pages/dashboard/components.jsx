import { useState, useEffect } from "react";
import {
  ArrowRight,
  CalendarClock,
  Clock,
  GraduationCap,
  Lightbulb,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Compass,
  Award,
  Info,
  Check,
  RotateCcw
} from "lucide-react";
import { topicsApi, dashboardApi } from "../../services/studyflowApi.js";
import {
  Badge,
  Button,
  Card,
  ProgressBar,
  ProgressRing,
  SectionHeader
} from "../../components/common.jsx";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../../components/ui/tooltip.jsx";
import { navigate } from "../../router.jsx";

const taskTypeLabels = {
  quiz: "Trắc nghiệm",
  flashcard: "Thẻ ghi nhớ",
  review: "Ôn tập",
  qa: "Hỏi AI",
  mock_test: "Thi thử",
  new: "Học mới",
  preview: "Chuẩn bị bài"
};

const statusLabels = {
  on_track: "Đúng tiến độ",
  needs_attention: "Cần chú ý",
  behind: "Chậm",
  not_enough_data: "Chưa đủ dữ liệu"
};

function courseTone(course) {
  if (course.priority === "high" || course.status === "needs_attention") return "green";
  if (course.priority === "medium") return "blue";
  return "gray";
}

function taskTone(type) {
  if (type === "quiz" || type === "new") return "green";
  if (type === "flashcard" || type === "preview") return "blue";
  if (type === "qa") return "violet";
  return "neutral";
}

function formatTimeRange(task) {
  if (!task?.startAt || !task?.endAt) return `${task?.durationMinutes || 0} phút`;
  const start = new Date(task.startAt).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  const end = new Date(task.endAt).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  return `${start} - ${end}`;
}

function startTask(task) {
  if (!task) return;
  if (task.type === "qa" || task.type === "review" || task.type === "new" || task.type === "preview") navigate(`/courses/detail/${task.courseId}`);
  else navigate(`/study/${task.courseId}?task=${task.id}`);
}

export function FocusCard({ task, courseById }) {
  if (!task) {
    return (
      <Card className="focus-card">
        <div className="focus-icon"><GraduationCap size={22} /></div>
        <div className="focus-main">
          <Badge tone="neutral">Hôm nay</Badge>
          <h2>Chưa có nhiệm vụ học</h2>
          <p>Tạo lịch học để StudyFlow đề xuất việc cần làm tiếp theo.</p>
        </div>
        <div className="focus-actions">
          <Button variant="primary" icon={CalendarClock} onClick={() => navigate("/schedule")}>Tạo lịch</Button>
        </div>
      </Card>
    );
  }

  const course = courseById.get(task.courseId);
  const isDone = task.status === "done";

  return (
    <Card className={`focus-card ${isDone ? "completed" : ""}`} style={isDone ? { opacity: 0.85, background: "linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%)", border: "1px solid #bbf7d0" } : {}}>
      <div className="focus-icon"><GraduationCap size={22} style={isDone ? { color: "#10b981" } : {}} /></div>
      <div className="focus-main">
        <Badge tone={isDone ? "green" : "green"}>{isDone ? "✓ Đã học xong" : "Ưu tiên hôm nay"}</Badge>
        <h2 style={isDone ? { textDecoration: "line-through", color: "#166534" } : {}}>{task.title}</h2>
        <p>{course?.name || "Môn học"} · {task.durationMinutes} phút</p>
        <div className="focus-reason">
          <Lightbulb size={16} />
          <span>Lý do: {task.reason || "Nhiệm vụ này được xếp theo ưu tiên học tập."}</span>
        </div>
        <ProgressBar value={course?.masteryPercent || 0} tone={isDone ? "green" : courseTone(course || {})} />
      </div>
      <div className="focus-actions">
        {!isDone && (
          <Button variant="primary" icon={ArrowRight} onClick={() => startTask(task)}>Bắt đầu học</Button>
        )}
      </div>
    </Card>
  );
}

export function TaskCard({ task, courseById }) {
  const course = courseById.get(task.courseId);
  const isDone = task.status === "done";

  return (
    <Card className={`task-card ${isDone ? "completed" : ""}`} style={isDone ? { opacity: 0.85, background: "linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%)", border: "1px solid #bbf7d0" } : {}}>
      <div className="task-meta">
        <Badge tone={isDone ? "green" : taskTone(task.type)}>{isDone ? "✓ Đã xong" : (taskTypeLabels[task.type] || task.type)}</Badge>
        <span><Clock size={14} /> {formatTimeRange(task)}</span>
      </div>
      <h3 style={isDone ? { textDecoration: "line-through", color: "#166534" } : {}}>{task.title}</h3>
      <p>{course?.name || "Môn học"}</p>
      <small>{task.reason || "Được tạo từ kế hoạch học."}</small>
      <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
        {!isDone && (
          <Button variant="ghost" size="sm" icon={ArrowRight} onClick={() => startTask(task)}>
            {task.type === "qa" ? "Mở chatbot" : "Làm ngay"}
          </Button>
        )}
      </div>
    </Card>
  );
}

export function CourseProgressCard({ courses }) {
  return (
    <Card className="stack-card">
      <SectionHeader title="Các môn học" action={<Button variant="ghost" size="sm" onClick={() => navigate("/courses")}>Xem tất cả</Button>} />
      <div className="list-stack">
        {courses.length ? courses.slice(0, 3).map((course) => {
          return (
            <div className="progress-row" key={course.id} onClick={() => navigate(`/courses/detail/${course.id}`)}>
              <div>
                <strong>
                  {course.name}
                </strong>
                <span>{course.currentWeek ? `Tuần ${course.currentWeek}` : (statusLabels[course.status] || course.status)} - {course.currentLesson?.title || course.activeBehavior}</span>
              </div>
              <span className="progress-value">{course.masteryPercent}% · {course.confidencePercent ?? 0}%</span>
              <ProgressBar value={course.masteryPercent} tone={courseTone(course)} />
            </div>
          );
        }) : <p className="empty-copy">Chưa có môn học nào.</p>}
      </div>
    </Card>
  );
}

export function WeakTopicsCard({ topics, courseById }) {
  return (
    <Card className="stack-card">
      <SectionHeader title="Chủ đề cần chú ý" />
      <div className="list-stack">
        {topics.length ? topics.map((topic) => (
          <div className="topic-row" key={topic.id}>
            <div>
              <strong>{topic.name}</strong>
              <span>{courseById.get(topic.courseId)?.name || "Môn học"} · Mastery {topic.masteryPercent}% · Tin cậy {topic.confidencePercent ?? 0}%</span>
            </div>
            <Button variant="secondary" size="sm" onClick={() => navigate(`/study/${topic.courseId}?topic=${topic.id}`)}>Luyện</Button>
          </div>
        )) : <p className="empty-copy">Chưa có topic yếu.</p>}
      </div>
    </Card>
  );
}

export function StatsPanel({ dashboard, courseById }) {
  const { weeklyStats, nearestDeadline, nextSchedule, courses } = dashboard;
  const nextCourse = nextSchedule ? courseById.get(nextSchedule.courseId) : null;

  return (
    <aside className="stats-panel">
      <Card className="stats-card">
        <h2>Thống kê học tập</h2>
        <div className="stats-summary">
          <ProgressRing value={weeklyStats.progressPercent} />
          <div className="stats-numbers">
            <span>Hoàn thành</span>
            <strong>{weeklyStats.completedTasks}/{weeklyStats.totalTasks} nhiệm vụ</strong>
            <span>Tuần này</span>
            <strong>{weeklyStats.minutesStudied} phút</strong>
            <span>Streak</span>
            <strong className="accent-orange">{weeklyStats.streakDays} ngày</strong>
          </div>
        </div>
        <div className="stats-divider" />
        <div className="mini-block danger-soft">
          <span>Deadline gần nhất</span>
          <strong>{nearestDeadline?.courseName || "Chưa có deadline"}</strong>
          <p>{nearestDeadline?.label || "Thêm ngày thi để theo dõi."}</p>
        </div>
        <div className="mini-block">
          <span>Lịch gần nhất</span>
          <strong>{nextSchedule ? `${formatTimeRange(nextSchedule)} · ${nextSchedule.title}` : "Chưa có lịch"}</strong>
          <p>{nextCourse?.name || "Tạo lịch học để bắt đầu."}</p>
        </div>
        <div className="mini-progress-list">
          <h3>Tiến độ môn</h3>
          {courses.slice(0, 3).map((course) => (
            <div key={course.id}>
              <div className="mini-progress-head">
                <span>{course.name}</span>
                <strong>{course.masteryPercent}% · {course.confidencePercent ?? 0}%</strong>
              </div>
              <ProgressBar value={course.masteryPercent} tone={courseTone(course)} />
            </div>
          ))}
        </div>
      </Card>
    </aside>
  );
}

export function CalibrationChart({ curveData }) {
  if (!curveData || curveData.length === 0) return <p className="empty-copy">Chưa có dữ liệu hiệu chuẩn.</p>;
  
  const size = 248;
  const padding = 34;
  const chartSize = size - padding * 2;
  
  const getX = (val) => padding + val * chartSize;
  const getY = (val) => padding + (1.0 - val) * chartSize;

  const validPoints = curveData.filter((d) => d.actual !== null);
  const averageGap = validPoints.length
    ? validPoints.reduce((sum, item) => sum + (item.actual - item.predicted), 0) / validPoints.length
    : 0;
  const absoluteGap = Math.round(Math.abs(averageGap) * 100);
  const summaryTone = averageGap > 0.08
    ? {
        badge: "Bạn đang vượt mức kỳ vọng",
        body: "Kết quả thực tế của bạn thường cao hơn mức kỳ vọng trung bình. Đây là dấu hiệu tốt để tăng dần độ khó hoặc nhịp học.",
        accent: "#15803d",
        soft: "#dcfce7"
      }
    : averageGap < -0.08
      ? {
          badge: "Bạn đang dưới mức kỳ vọng",
          body: "Kết quả thực tế của bạn đang thấp hơn mức kỳ vọng trung bình. Nên củng cố nền tảng trước khi tăng tốc hoặc học nội dung khó hơn.",
          accent: "#b45309",
          soft: "#fef3c7"
        }
      : {
          badge: "Bạn đang bám sát mức kỳ vọng",
          body: "Kết quả thực tế của bạn đang khá gần mức kỳ vọng trung bình. Đây là trạng thái ổn định để tối ưu lịch học tiếp theo.",
          accent: "#1d4ed8",
          soft: "#dbeafe"
        };
  
  const points = validPoints
    .map(d => `${getX(d.predicted)},${getY(d.actual)}`)
    .join(" ");

  return (
    <Card className="p-5">
      <div className="flex flex-col gap-4">
        <TooltipProvider delayDuration={120}>
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-foreground">Bạn và mức kỳ vọng trung bình</h3>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-border bg-background text-muted-foreground transition-colors hover:text-foreground"
                    aria-label="Thông tin thêm"
                  >
                    <Info size={14} />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[280px] whitespace-normal bg-foreground text-background">
                  <div className="space-y-2">
                    <p>Hệ thống đối chiếu kết quả thực tế của bạn với mức kỳ vọng trung bình để xem bạn đang vượt, thấp hơn hay bám sát mốc mong đợi.</p>
                    <p>Điểm càng gần đường chéo thì kết quả của bạn càng cân bằng với mức kỳ vọng.</p>
                    <p>{summaryTone.body}</p>
                  </div>
                </TooltipContent>
              </Tooltip>
            </div>
            <span
              className="text-[11px] font-semibold px-3 py-1 rounded-full"
              style={{ color: summaryTone.accent, backgroundColor: summaryTone.soft }}
            >
              {summaryTone.badge}
            </span>
          </div>
          <div className="rounded-lg border border-border bg-muted/30 px-3 py-3">
            <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Độ lệch trung bình</div>
            <div className="mt-1 text-xl font-bold text-foreground">{absoluteGap}%</div>
            <div className="mt-1 text-[11px] text-muted-foreground">Hover vào icon để xem diễn giải chi tiết.</div>
          </div>
        </div>
        </TooltipProvider>
        <div className="relative w-full flex justify-center rounded-xl border border-border bg-gradient-to-b from-white to-[#f6faf2] px-3 py-4">
          <svg width="100%" viewBox={`0 0 ${size} ${size}`} className="max-w-[280px]">
            <defs>
              <linearGradient id="calibration-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.18" />
                <stop offset="100%" stopColor="var(--primary)" stopOpacity="0.03" />
              </linearGradient>
            </defs>
          {/* Grid lines */}
          <line x1={padding} y1={padding} x2={padding + chartSize} y2={padding} stroke="var(--border)" strokeWidth="0.5" strokeDasharray="2" />
          <line x1={padding} y1={padding + chartSize / 2} x2={padding + chartSize} y2={padding + chartSize / 2} stroke="var(--border)" strokeWidth="0.5" strokeDasharray="2" />
          <line x1={padding + chartSize / 2} y1={padding} x2={padding + chartSize / 2} y2={padding + chartSize} stroke="var(--border)" strokeWidth="0.5" strokeDasharray="2" />
          <line x1={padding + chartSize} y1={padding} x2={padding + chartSize} y2={padding + chartSize} stroke="var(--border)" strokeWidth="0.5" strokeDasharray="2" />
          
          {/* Ideal Line (Diagonal y=x) */}
          <line x1={getX(0)} y1={getY(0)} x2={getX(1)} y2={getY(1)} stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="4" />
          
          {/* Actual Calibration Line */}
          {points ? (
            <polygon
              fill="url(#calibration-area)"
              points={`${getX(0)},${getY(0)} ${points} ${getX(1)},${getY(0)}`}
              opacity="0.55"
            />
          ) : null}
          {points && <polyline fill="none" stroke="var(--primary)" strokeWidth="2.5" points={points} strokeLinecap="round" strokeLinejoin="round" />}
          
          {/* Data points */}
          {validPoints.map((d, i) => {
            if (d.actual === null) return null;
            const cx = getX(d.predicted);
            const cy = getY(d.actual);
            return (
              <g key={i} className="group cursor-pointer">
                <circle cx={cx} cy={cy} r="4.5" fill="var(--card)" stroke="var(--primary)" strokeWidth="2" />
                <title>{`Khoảng ${d.bin}: Kỳ vọng ${Math.round(d.predicted * 100)}%, Thực tế ${Math.round(d.actual * 100)}% (${d.count} bài)`}</title>
              </g>
            );
          })}
          
          {/* Axes */}
          <line x1={padding} y1={padding + chartSize} x2={padding + chartSize} y2={padding + chartSize} stroke="var(--foreground)" strokeWidth="1" />
          <line x1={padding} y1={padding} x2={padding} y2={padding + chartSize} stroke="var(--foreground)" strokeWidth="1" />
          
          {/* Axis Labels */}
          <text x={padding + chartSize / 2} y={size - 6} textAnchor="middle" fontSize="8" fill="var(--muted-foreground)">Mức kỳ vọng trung bình</text>
          <text x={11} y={padding + chartSize / 2} textAnchor="middle" fontSize="8" fill="var(--muted-foreground)" transform={`rotate(-90, 11, ${padding + chartSize / 2})`}>Kết quả thật của bạn</text>
        </svg>
        </div>
        <div className="flex gap-4 text-[11px] text-muted-foreground justify-center flex-wrap">
          <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-slate-400 inline-block border-t border-dashed"></span> Mốc kỳ vọng trung bình</span>
          <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-[var(--primary)] inline-block"></span> Dữ liệu của bạn</span>
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full border-2 border-[var(--primary)] inline-block"></span> Mỗi chấm là một nhóm bài đã làm</span>
        </div>
      </div>
    </Card>
  );
}

export function MasteryTrendChart({ trends }) {
  if (!trends || trends.length === 0) return <p className="empty-copy">Chưa có dữ liệu xu hướng.</p>;
  
  const sizeX = 350;
  const sizeY = 150;
  const paddingX = 35;
  const paddingY = 20;
  const chartWidth = sizeX - paddingX * 2;
  const chartHeight = sizeY - paddingY * 2;
  
  const points = trends.map((t, idx) => {
    const x = paddingX + (idx / (trends.length - 1)) * chartWidth;
    const y = paddingY + (1.0 - t.mastery) * chartHeight;
    return { x, y, val: t.mastery, date: t.date };
  });
  
  const polylinePoints = points.map(p => `${p.x},${p.y}`).join(" ");
  const areaPoints = `${paddingX},${sizeY - paddingY} ` + polylinePoints + ` ${sizeX - paddingX},${sizeY - paddingY}`;

  return (
    <Card className="flex flex-col items-center p-4">
      <h3 className="text-sm font-semibold mb-4 text-center">Xu hướng Mastery (14 ngày qua)</h3>
      <div className="relative w-full flex justify-center">
        <svg width="100%" viewBox={`0 0 ${sizeX} ${sizeY}`} className="w-full">
          <defs>
            <linearGradient id="trend-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.3" />
              <stop offset="100%" stopColor="var(--primary)" stopOpacity="0.0" />
            </linearGradient>
          </defs>
          
          {/* Grid lines */}
          <line x1={paddingX} y1={paddingY} x2={sizeX - paddingX} y2={paddingY} stroke="var(--border)" strokeWidth="0.5" strokeDasharray="2" />
          <line x1={paddingX} y1={paddingY + chartHeight / 2} x2={sizeX - paddingX} y2={paddingY + chartHeight / 2} stroke="var(--border)" strokeWidth="0.5" strokeDasharray="2" />
          <line x1={paddingX} y1={sizeY - paddingY} x2={sizeX - paddingX} y2={sizeY - paddingY} stroke="var(--border)" strokeWidth="0.5" strokeDasharray="2" />

          {/* Filled Area */}
          <polygon points={areaPoints} fill="url(#trend-gradient)" />
          
          {/* Line */}
          <polyline fill="none" stroke="var(--primary)" strokeWidth="2.5" points={polylinePoints} strokeLinecap="round" strokeLinejoin="round" />
          
          {/* Points */}
          {points.map((p, i) => (
            <g key={i} className="group cursor-pointer">
              <circle cx={p.x} cy={p.y} r="3" fill="var(--card)" stroke="var(--primary)" strokeWidth="1.5" />
              <title>{`Ngày ${p.date}: Mastery ${Math.round(p.val * 100)}%`}</title>
            </g>
          ))}
          
          {/* Axis Labels */}
          <text x={paddingX} y={sizeY - 4} fontSize="8" fill="var(--muted-foreground)" textAnchor="start">
            {new Date(trends[0].date).toLocaleDateString("vi-VN", { month: "numeric", day: "numeric" })}
          </text>
          <text x={sizeX - paddingX} y={sizeY - 4} fontSize="8" fill="var(--muted-foreground)" textAnchor="end">
            {new Date(trends[trends.length - 1].date).toLocaleDateString("vi-VN", { month: "numeric", day: "numeric" })}
          </text>
        </svg>
      </div>
    </Card>
  );
}

export function ProfileDashboardView({ dashboard }) {
  const metrics = dashboard?.profileMetrics;
  const courses = dashboard?.courses || [];
  const [selectedCourseId, setSelectedCourseId] = useState(courses[0]?.id || "");
  useEffect(() => {
    if (!courses.length) {
      setSelectedCourseId("");
      return;
    }

    setSelectedCourseId((current) => (
      current && courses.some((course) => course.id === current) ? current : courses[0].id
    ));
  }, [courses]);
  
  if (!metrics) {
    return <Card className="p-6">Chưa có đủ dữ liệu hồ sơ năng lực AI.</Card>;
  }

  const selectedCourse = courses.find((course) => course.id === selectedCourseId) || courses[0] || null;
  const activeMetrics = (selectedCourse?.id && metrics?.byCourse?.[selectedCourse.id]) || metrics;
  const selectedCourseMastery = selectedCourse?.masteryPercent || 0;
  const selectedCourseConfidence = selectedCourse?.confidencePercent || 0;
  const hasSelectedCourseData = selectedCourseMastery > 0 || selectedCourseConfidence > 0 || (activeMetrics?.eventCount || 0) > 0 || (activeMetrics?.topicCount || 0) > 0;
  const {
    knowledgeConsistency,
    retentionReliability,
    personalCalibrationScore,
    calibrationGap,
    engagementConfidence,
    calibrationCurve,
    masteryTrends
  } = activeMetrics;
  const displayKnowledgeConsistency = hasSelectedCourseData ? knowledgeConsistency : 0;
  const displayRetentionReliability = hasSelectedCourseData ? retentionReliability : 0;
  const displayPersonalCalibrationScore = hasSelectedCourseData ? personalCalibrationScore : 0;
  const displayCalibrationGap = hasSelectedCourseData ? calibrationGap : 0;
  const displayEngagementConfidence = hasSelectedCourseData ? engagementConfidence : 0;
  const displayCalibrationCurve = hasSelectedCourseData ? calibrationCurve : [];
  const displayMasteryTrends = hasSelectedCourseData ? masteryTrends : [];

  return (
    <div className="profile-metrics-view flex flex-col gap-6">
      <Card className="stack-card">
        <SectionHeader
          title="Môn học đang xem"
          subtitle="Chọn môn ở đây để toàn bộ số liệu bên dưới hiển thị đúng theo môn học đó."
        />
        <div className="mt-4 flex flex-wrap gap-2">
          {courses.map((course) => {
            const active = course.id === selectedCourseId;
            return (
              <button
                key={course.id}
                type="button"
                onClick={() => setSelectedCourseId(course.id)}
                className={`min-w-[160px] max-w-[260px] rounded-lg border px-4 py-2.5 text-left text-sm transition-colors ${
                  active
                    ? "border-[var(--primary)] bg-[color:var(--primary-soft)] text-foreground shadow-sm"
                    : "border-border bg-background text-muted-foreground hover:border-[var(--primary)] hover:text-foreground"
                }`}
              >
                <div className="truncate font-semibold">{course.name}</div>
                <div className="mt-1 text-[11px]">
                  {course.masteryPercent || 0}% mastery · {course.confidencePercent || 0}% tin cậy
                </div>
              </button>
            );
          })}
        </div>
        {selectedCourse ? (
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Mastery trung bình của môn</div>
              <div className="mt-1 text-lg font-bold text-foreground">{selectedCourseMastery}%</div>
            </div>
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Confidence trung bình của môn</div>
              <div className="mt-1 text-lg font-bold text-foreground">{selectedCourseConfidence}%</div>
            </div>
          </div>
        ) : null}
      </Card>

      {/* 4 Multi-dimensional Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Consistency */}
        <div className="flex flex-col bg-card p-5 rounded-xl border border-border shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 w-12 h-12 bg-emerald-500/10 rounded-bl-full flex items-start justify-end p-2 text-emerald-600">
            <Compass size={18} />
          </div>
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Độ ổn định kiến thức</span>
          <div className="flex items-baseline gap-1 mt-2">
            <span className="text-2xl font-bold text-foreground">{displayKnowledgeConsistency}%</span>
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
              displayKnowledgeConsistency >= 85 ? "bg-green-100 text-green-700 dark:bg-green-950/30 dark:text-green-400" :
              displayKnowledgeConsistency >= 70 ? "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400" :
              "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400"
            }`}>
              {!hasSelectedCourseData ? "Chưa có dữ liệu" : displayKnowledgeConsistency >= 85 ? "Đồng đều" : displayKnowledgeConsistency >= 70 ? "Khá tốt" : "Lệch tủ"}
            </span>
          </div>
          <p className="text-[11px] mt-3 text-muted-foreground leading-relaxed flex-grow">
            {knowledgeConsistency >= 85 
              ? "Kiến thức của bạn phân bố rất đồng đều ở mọi chủ đề." 
              : knowledgeConsistency >= 70 
              ? "Bạn đang học khá đều nhưng có một số chủ đề cần chú ý." 
              : "Có sự chênh lệch lớn giữa các chủ đề. Tránh học lệch tủ."}
          </p>
          <div className="mt-4 pt-3 border-t border-border flex items-center gap-1 text-[9px] text-muted-foreground">
            <Info size={10} />
            <span>Đo lường độ ổn định (1 - StdDev)</span>
          </div>
        </div>

        {/* Retention */}
        <div className="flex flex-col bg-card p-5 rounded-xl border border-border shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 w-12 h-12 bg-blue-500/10 rounded-bl-full flex items-start justify-end p-2 text-blue-600">
            <ShieldCheck size={18} />
          </div>
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Độ tin cậy ghi nhớ</span>
          <div className="flex items-baseline gap-1 mt-2">
            <span className="text-2xl font-bold text-foreground">{displayRetentionReliability}%</span>
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
              displayRetentionReliability >= 85 ? "bg-green-100 text-green-700 dark:bg-green-950/30 dark:text-green-400" :
              displayRetentionReliability >= 70 ? "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400" :
              "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400"
            }`}>
              {!hasSelectedCourseData ? "Chưa có dữ liệu" : displayRetentionReliability >= 85 ? "Ổn định" : displayRetentionReliability >= 70 ? "Bình thường" : "Quên nhiều"}
            </span>
          </div>
          <p className="text-[11px] mt-3 text-muted-foreground leading-relaxed flex-grow">
            {retentionReliability >= 85 
              ? "Tuyệt vời! Bạn đang ôn tập đúng thời điểm vàng (trước khi quên)." 
              : retentionReliability >= 70 
              ? "Có một vài chủ đề sắp quá hạn ôn tập theo FSRS." 
              : "Nhiều chủ đề đã học bị quá hạn ôn tập. Cần ôn ngay."}
          </p>
          <div className="mt-4 pt-3 border-t border-border flex items-center gap-1 text-[9px] text-muted-foreground">
            <Info size={10} />
            <span>% topic chưa quá hạn FSRS</span>
          </div>
        </div>

        {/* Calibration */}
        <div className="flex flex-col bg-card p-5 rounded-xl border border-border shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 w-12 h-12 bg-amber-500/10 rounded-bl-full flex items-start justify-end p-2 text-amber-600">
            <Award size={18} />
          </div>
          <div className="flex items-center gap-2 pr-8">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Bạn và mức kỳ vọng trung bình</span>
            <TooltipProvider delayDuration={120}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    className="inline-flex h-5 w-5 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground"
                    aria-label="Thông tin thêm"
                  >
                    <Info size={12} />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[260px] whitespace-normal bg-foreground text-background">
                  Hệ thống đối chiếu kết quả thực tế của bạn với mức kỳ vọng trung bình để đánh giá bạn đang vượt, thấp hơn hay bám sát mốc mong đợi.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          <div className="flex items-baseline gap-1 mt-2">
            <span className="text-2xl font-bold text-foreground">{displayPersonalCalibrationScore}%</span>
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
              displayPersonalCalibrationScore >= 85 ? "bg-green-100 text-green-700 dark:bg-green-950/30 dark:text-green-400" :
              displayPersonalCalibrationScore >= 70 ? "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400" :
              "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400"
            }`}>
              {!hasSelectedCourseData ? "Chưa có dữ liệu" : displayPersonalCalibrationScore >= 85 ? "Chính xác cao" : displayPersonalCalibrationScore >= 70 ? "Khá chính xác" : "Lệch nhiều"}
            </span>
          </div>
          <div className="mt-3 text-[11px] text-muted-foreground flex-grow">Hover để xem diễn giải chi tiết.</div>
          <div className="mt-4 pt-3 border-t border-border flex items-center gap-1 text-[9px] text-muted-foreground">
            <Info size={10} />
            <span>Độ lệch giữa mức kỳ vọng và kết quả thật: {displayCalibrationGap}%</span>
          </div>
        </div>

        {/* Confidence */}
        <div className="flex flex-col bg-card p-5 rounded-xl border border-border shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 w-12 h-12 bg-indigo-500/10 rounded-bl-full flex items-start justify-end p-2 text-indigo-600">
            <TrendingUp size={18} />
          </div>
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Độ tự tin học tập</span>
          <div className="flex items-baseline gap-1 mt-2">
            <span className="text-2xl font-bold text-foreground">{displayEngagementConfidence}%</span>
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
              displayEngagementConfidence >= 80 ? "bg-green-100 text-green-700 dark:bg-green-950/30 dark:text-green-400" :
              displayEngagementConfidence >= 50 ? "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400" :
              "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400"
            }`}>
              {!hasSelectedCourseData ? "Chưa có dữ liệu" : displayEngagementConfidence >= 80 ? "Tin cậy cao" : displayEngagementConfidence >= 50 ? "Trung bình" : "Cần tích lũy"}
            </span>
          </div>
          <p className="text-[11px] mt-3 text-muted-foreground leading-relaxed flex-grow">
            {engagementConfidence >= 80 
              ? "Hồ sơ năng lực có độ tin cậy tuyệt đối nhờ lượng tương tác lớn." 
              : engagementConfidence >= 50 
              ? "Tương tác ở mức trung bình. Hãy luyện tập thêm." 
              : "AI cần thêm bằng chứng kiểm thử (quiz/flashcard) để hiểu bạn hơn."}
          </p>
          <div className="mt-4 pt-3 border-t border-border flex items-center gap-1 text-[9px] text-muted-foreground">
            <Info size={10} />
            <span>Độ tự tin weighted theo bằng chứng</span>
          </div>
        </div>
      </div>

      {/* 2-Column charts section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CalibrationChart curveData={displayCalibrationCurve} />
        <MasteryTrendChart trends={displayMasteryTrends} />
      </div>

      {/* Explainable Diagnostics / evidence info table */}
      <Card className="stack-card">
        <SectionHeader 
          title="Chi tiết Đánh giá & Bằng chứng học tập" 
          subtitle="Báo cáo giải thích nguồn và mức độ tin cậy của từng chủ đề học tập." 
        />
        {selectedCourse ? (
          <div className="mt-4 grid grid-cols-1 lg:grid-cols-4 gap-3">
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Môn đang xem</div>
              <div className="mt-1 text-sm font-semibold text-foreground">{selectedCourse.name}</div>
            </div>
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Mastery hiện tại</div>
              <div className="mt-1 text-sm font-semibold text-foreground">{selectedCourse.masteryPercent || 0}%</div>
            </div>
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Độ tin cậy</div>
              <div className="mt-1 text-sm font-semibold text-foreground">{selectedCourse.confidencePercent || 0}%</div>
            </div>
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Ngày thi</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {selectedCourse.examDate ? new Date(selectedCourse.examDate).toLocaleDateString("vi-VN") : "Chưa đặt"}
              </div>
            </div>
          </div>
        ) : null}
        <CourseTopicsTable course={selectedCourse} />
        {false ? <div className="TEST_MARKER">
          <table className="w-full text-left text-xs border-collapse min-w-[500px]">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-[10px] font-bold uppercase tracking-wider">
                <th className="py-3 px-4">Chủ đề (Topic/Subtopic)</th>
                <th className="py-3 px-4 text-center">BKT Mastery</th>
                <th className="py-3 px-4 text-center">Độ tự tin (Confidence)</th>
                <th className="py-3 px-4">Nguồn bằng chứng</th>
                <th className="py-3 px-4 text-center">Trạng thái ôn tập</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {dashboard.courses.map((course) => (
                <CourseTopicsRows key={course.id} courseId={course.id} courseName={course.name} />
              ))}
            </tbody>
          </table>
        </div> : null}
      </Card>
    </div>
  );
}

function CourseTopicsRows({ courseId, courseName }) {
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    topicsApi.getTopics(courseId)
      .then(setTopics)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [courseId]);

  if (loading) {
    return (
      <tr>
        <td colSpan="5" className="py-3 px-4 text-muted-foreground italic text-center">Đang tải chi tiết môn {courseName}...</td>
      </tr>
    );
  }

  if (!topics || topics.length === 0) {
    return (
      <tr>
        <td colSpan="5" className="py-3 px-4 text-muted-foreground italic text-center">Môn {courseName} chưa có chủ đề.</td>
      </tr>
    );
  }

  return (
    <>
      <tr className="bg-muted/40 font-semibold text-accent-foreground">
        <td colSpan="5" className="py-2.5 px-4">{courseName}</td>
      </tr>
      {topics.map((topic) => {
        const sourceLabels = {
          self_assessment: "Tự đánh giá",
          quiz: "Kiểm tra ngắn",
          flashcard: "Thẻ ghi nhớ",
          none: "Chưa có bằng chứng"
        };
        const tone = topic.masteryPercent >= 75 ? "green" : topic.masteryPercent >= 50 ? "amber" : "rose";
        return (
          <tr key={topic.id} className="hover:bg-muted/10 transition-colors">
            <td className="py-3 px-4 font-medium text-foreground pl-8">{topic.name}</td>
            <td className="py-3 px-4 text-center">
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-${tone === "rose" ? "red" : tone}-100 dark:bg-${tone === "rose" ? "red" : tone}-950/20 text-${tone === "rose" ? "red" : tone}-700 dark:text-${tone === "rose" ? "red" : tone}-400`}>
                {topic.masteryPercent}%
              </span>
            </td>
            <td className="py-3 px-4 text-center">
              <div className="flex items-center justify-center gap-1">
                <span className="font-semibold">{topic.confidencePercent}%</span>
                <span className="text-[9px] text-muted-foreground">({topic.masteryConfidence >= 0.75 ? "Cao" : topic.masteryConfidence >= 0.4 ? "Trung bình" : "Thấp"})</span>
              </div>
            </td>
            <td className="py-3 px-4">
              <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-2 py-0.5 rounded">
                {sourceLabels[topic.masteryEvidenceSource] || topic.masteryEvidenceSource}
              </span>
            </td>
            <td className="py-3 px-4 text-center">
              {topic.dueReviewAt ? (
                new Date(topic.dueReviewAt) <= new Date() ? (
                  <span className="text-red-600 font-semibold">Quá hạn ôn tập</span>
                ) : (
                  <span className="text-green-600 font-semibold">Ổn định (Còn hạn)</span>
                )
              ) : (
                <span className="text-muted-foreground">Chưa có lịch ôn</span>
              )}
            </td>
          </tr>
        );
      })}
    </>
  );
}

function CourseTopicsTable({ course }) {
  const courseId = course?.id;
  const courseName = course?.name || "môn học";
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!courseId) {
      setTopics([]);
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    topicsApi.getTopics(courseId)
      .then((items) => {
        if (!active) return;
        setTopics(items || []);
      })
      .catch(() => {
        if (!active) return;
        setTopics([]);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [courseId]);

  if (!courseId) {
    return null;
  }

  return (
    <div className="overflow-x-auto w-full mt-4">
      <table className="w-full text-left text-xs border-collapse min-w-[500px]">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-[10px] font-bold uppercase tracking-wider">
            <th className="py-3 px-4">Chủ đề (Topic/Subtopic)</th>
            <th className="py-3 px-4 text-center">BKT Mastery</th>
            <th className="py-3 px-4 text-center">Độ tin cậy (Confidence)</th>
            <th className="py-3 px-4">Nguồn bằng chứng</th>
            <th className="py-3 px-4 text-center">Trạng thái ôn tập</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {loading ? (
            <tr>
              <td colSpan="5" className="py-3 px-4 text-muted-foreground italic text-center">Đang tải chi tiết môn {courseName}...</td>
            </tr>
          ) : null}
          {!loading && (!topics || topics.length === 0) ? (
            <tr>
              <td colSpan="5" className="py-3 px-4 text-muted-foreground italic text-center">Môn {courseName} chưa có chủ đề.</td>
            </tr>
          ) : null}
          {!loading ? topics.map((topic) => {
            const sourceLabels = {
              self_assessment: "Tự đánh giá",
              quiz: "Kiểm tra ngắn",
              flashcard: "Thẻ ghi nhớ",
              none: "Chưa có bằng chứng"
            };
            const masteryToneClass = topic.masteryPercent >= 75
              ? "bg-green-100 text-green-700 dark:bg-green-950/20 dark:text-green-400"
              : topic.masteryPercent >= 50
                ? "bg-amber-100 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400"
                : "bg-red-100 text-red-700 dark:bg-red-950/20 dark:text-red-400";
            return (
              <tr key={topic.id} className="hover:bg-muted/10 transition-colors">
                <td className="py-3 px-4 font-medium text-foreground">{topic.name}</td>
                <td className="py-3 px-4 text-center">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${masteryToneClass}`}>
                    {topic.masteryPercent}%
                  </span>
                </td>
                <td className="py-3 px-4 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <span className="font-semibold">{topic.confidencePercent}%</span>
                    <span className="text-[9px] text-muted-foreground">({topic.masteryConfidence >= 0.75 ? "Cao" : topic.masteryConfidence >= 0.4 ? "Trung bình" : "Thấp"})</span>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-2 py-0.5 rounded">
                    {sourceLabels[topic.masteryEvidenceSource] || topic.masteryEvidenceSource}
                  </span>
                </td>
                <td className="py-3 px-4 text-center">
                  {topic.dueReviewAt ? (
                    new Date(topic.dueReviewAt) <= new Date() ? (
                      <span className="text-red-600 font-semibold">Quá hạn ôn tập</span>
                    ) : (
                      <span className="text-green-600 font-semibold">Ổn định (Còn hạn)</span>
                    )
                  ) : (
                    <span className="text-muted-foreground">Chưa có lịch ôn</span>
                  )}
                </td>
              </tr>
            );
          }) : null}
        </tbody>
      </table>
    </div>
  );
}
