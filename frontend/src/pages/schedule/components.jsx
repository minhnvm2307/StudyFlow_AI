import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Ban,
  CalendarPlus,
  ChevronLeft,
  ChevronRight,
  Clock,
  Edit3,
  FileText,
  Play,
  Plus,
  RotateCcw,
  Trash2,
  X,
  Check,
  HelpCircle
} from "lucide-react";
import { Badge, Button, Card, IconButton, Modal } from "../../components/common.jsx";
import { navigate } from "../../router.jsx";

const taskTypeLabels = {
  quiz: "Trắc nghiệm",
  flashcard: "Thẻ ghi nhớ",
  review: "Ôn tập",
  qa: "Hỏi AI",
  mock_test: "Thi thử",
  new: "Học mới",
  preview: "Chuẩn bị bài",
  busy: "Bận",
  exam: "Lịch thi",
  class: "Lịch học trường"
};
const taskColors = { quiz: "green", flashcard: "blue", review: "purple", qa: "purple", mock_test: "pink", new: "green", preview: "blue" };

export const getSubjectColor = (subjectId) => {
  const palette = [
    { name: "Blue", main: "#3b82f6", bg: "#eff6ff", border: "#bfdbfe", text: "#1e3a8a" },
    { name: "Emerald", main: "#10b981", bg: "#ecfdf5", border: "#a7f3d0", text: "#064e3b" },
    { name: "Violet", main: "#8b5cf6", bg: "#f5f3ff", border: "#ddd6fe", text: "#3b0764" },
    { name: "Amber", main: "#f59e0b", bg: "#fffbeb", border: "#fde68a", text: "#78350f" },
    { name: "Teal", main: "#0d9488", bg: "#f0fdfa", border: "#99f6e4", text: "#115e59" },
    { name: "Indigo", main: "#4f46e5", bg: "#eef2ff", border: "#c7d2fe", text: "#312e81" },
    { name: "Orange", main: "#f97316", bg: "#fff7ed", border: "#ffedd5", text: "#7c2d12" },
    { name: "Pink", main: "#ec4899", bg: "#fdf2f8", border: "#fbcfe8", text: "#9d174d" }
  ];
  if (!subjectId) return palette[0];
  // Simple hash function
  let hash = 0;
  for (let i = 0; i < subjectId.length; i++) {
    hash = subjectId.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % palette.length;
  return palette[index];
};

export function startOfWeek(date) {
  const copy = new Date(date);
  const day = copy.getDay() || 7;
  copy.setDate(copy.getDate() - day + 1);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export function addDays(date, days) {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function formatDateInput(date) {
  return formatDateKey(date);
}

function formatDateKey(date) {
  const value = new Date(date);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatTime(date) {
  return new Date(date).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function toTimeInput(date) {
  const value = new Date(date);
  return `${String(value.getHours()).padStart(2, "0")}:${String(value.getMinutes()).padStart(2, "0")}`;
}

function eventDuration(startAt, endAt) {
  const minutes = Math.max(1, Math.round((new Date(endAt) - new Date(startAt)) / 60000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

export function buildDays(weekStart) {
  return Array.from({ length: 7 }, (_, index) => {
    const date = addDays(weekStart, index);
    const today = new Date();
    return {
      key: formatDateKey(date),
      label: ["T2", "T3", "T4", "T5", "T6", "T7", "CN"][index],
      dateLabel: date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" }),
      today: date.toDateString() === today.toDateString(),
      date
    };
  });
}

export function HourAxis() {
  const hours = Array.from({ length: 24 }, (_, i) => i);
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      borderRight: "1px solid #edf0f2",
      background: "#fdfdfd",
      minHeight: "100%",
      position: "relative"
    }}>
      {/* Sticky top spacer matching day headers */}
      <div style={{
        position: "sticky",
        top: 0,
        zIndex: 10,
        height: "68px",
        borderBottom: "1px solid #edf0f2",
        backgroundColor: "#fdfdfd"
      }} />
      
      {hours.map((hour) => (
        <div
          key={hour}
          style={{
            height: "60px",
            fontSize: "11px",
            color: "#64748b",
            fontWeight: "600",
            textAlign: "center",
            boxSizing: "border-box",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderBottom: "1px solid #f1f5f9"
          }}
        >
          {`${String(hour).padStart(2, "0")}:00`}
        </div>
      ))}
    </div>
  );
}

export function DaySchedule({ day, items, courseById, onSelect }) {
  const dayItems = items
    .filter((item) => (item.segmentDateKey || formatDateKey(item.startAt)) === day.key)
    .sort((a, b) => new Date(a.startAt) - new Date(b.startAt));

  // Overlap placement algorithm
  const sorted = [...dayItems].sort((a, b) => new Date(a.startAt) - new Date(b.startAt));
  const columns = [];
  sorted.forEach((event) => {
    let placed = false;
    const start = new Date(event.startAt);
    
    for (let i = 0; i < columns.length; i++) {
      const lastEvent = columns[i][columns[i].length - 1];
      const lastEnd = new Date(lastEvent.endAt);
      if (start >= lastEnd) {
        columns[i].push(event);
        placed = true;
        break;
      }
    }
    
    if (!placed) {
      columns.push([event]);
    }
  });

  const eventLayouts = new Map();
  columns.forEach((col, colIdx) => {
    col.forEach((event) => {
      eventLayouts.set(event.id, {
        left: `${(colIdx / columns.length) * 100}%`,
        width: `${(1 / columns.length) * 100}%`
      });
    });
  });

  const hours = Array.from({ length: 24 }, (_, i) => i);

  return (
    <section className={`day-stack ${day.today ? "today" : ""}`} style={{ position: "relative", minWidth: "136px" }}>
      <div className="day-stack-head">
        <span>{day.label}</span>
        <strong>{day.dateLabel}</strong>
      </div>
      
      <div style={{ position: "relative", height: "1440px", backgroundColor: "#ffffff" }}>
        {/* Hour row grid lines */}
        {hours.map((hour) => (
          <div
            key={hour}
            style={{
              height: "60px",
              borderBottom: "1px solid #f1f5f9",
              boxSizing: "border-box"
            }}
          />
        ))}

        {/* Absolute positioned cards */}
        {dayItems.map((item) => {
          const start = new Date(item.startAt);
          const end = new Date(item.endAt);
          const startMinutes = start.getHours() * 60 + start.getMinutes();
          const endMinutes = end.getHours() * 60 + end.getMinutes();
          const duration = Math.max(35, endMinutes - startMinutes); // Min 35px height
          const layout = eventLayouts.get(item.id) || { left: "0%", width: "100%" };

          return (
            <div
              key={`${item.itemKind}-${item.id}`}
              style={{
                position: "absolute",
                top: `${startMinutes}px`,
                height: `${duration}px`,
                left: `calc(${layout.left} + 4px)`,
                width: `calc(${layout.width} - 8px)`,
                zIndex: 5,
                boxSizing: "border-box"
              }}
            >
              <EventCard
                item={item}
                courseById={courseById}
                onSelect={onSelect}
                isAbsolute
              />
            </div>
          );
        })}
      </div>
    </section>
  );
}

function EventCard({ item, courseById, onSelect, isAbsolute = false }) {
  const isBusy = item.itemKind === "busy";
  const isExam = item.itemKind === "exam";
  const isClass = item.itemKind === "class";
  const isTask = !isBusy && !isExam && !isClass;
  const course = item.courseId ? courseById.get(item.courseId) : null;
  const courseName = course?.name || item.courseName || item.subjectName || "";
  const scopeLine = isTask ? taskScopeLine(item) : "";
  const masteryRows = isTask ? taskMasteryRows(item) : [];
  const cardTitle = isTask && item.topicStats?.title ? `${taskActionLabel(item.type)}: ${item.topicStats.title}` : item.title;
  const subtitle = isBusy
    ? (item.reason || "Không thể tham gia")
    : isClass
      ? (course?.name || "Môn học")
      : (item.lessonTitle || course?.currentLesson?.title || course?.name || "Môn học");

  // Determine if this is an exam card (has special highlight)
  const isExamCard =
    isExam ||
    (item.type === "diagnostic" || item.type === "mock_test") ||
    (typeof item.title === "string" && (item.title.includes("Thi") || item.title.toLowerCase().includes("exam"))) ||
    (typeof item.lessonTitle === "string" && (item.lessonTitle.includes("Thi") || item.lessonTitle.toLowerCase().includes("exam")));

  const durationMins = Math.max(1, Math.round((new Date(item.endAt) - new Date(item.startAt)) / 60000));

  if (isBusy) {
    return (
      <button
        type="button"
        className="calendar-event"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "flex-start",
          overflow: "hidden",
          borderRadius: "8px",
          padding: isAbsolute ? "6px 8px" : "9px 10px 24px",
          textAlign: "left",
          transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
          background: "linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)",
          border: "1px solid #cbd5e1",
          borderLeft: "4px solid #94a3b8",
          color: "#475569",
          position: "relative",
          width: isAbsolute ? "100%" : "auto",
          height: isAbsolute ? "100%" : "auto",
          boxShadow: "0 1px 2px rgba(0,0,0,0.03)"
        }}
        onClick={() => onSelect({ ...item, color: "busy" })}
      >
        <span className="event-time" style={{ color: "#64748b", fontWeight: 700, fontSize: "10px" }}>
          {item.displayStartTime || formatTime(item.startAt)} - {item.displayEndTime || formatTime(item.endAt)}
        </span>
        {(!isAbsolute || durationMins >= 45) && (
          <div style={{ display: "flex", alignItems: "center", gap: "4px", backgroundColor: "#e2e8f0", color: "#475569", padding: "1px 6px", borderRadius: "4px", fontSize: "9px", fontWeight: "bold", width: "fit-content", marginTop: "4px" }}>
            🚫 Bận
          </div>
        )}
        <strong style={{ fontSize: "12px", lineHeight: "1.2", marginTop: "4px", color: "#334155", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%", fontWeight: 600 }}>
          {cardTitle}
        </strong>
        {(!isAbsolute || durationMins >= 60) && (
          <small style={{ marginTop: "3px", fontSize: "11px", color: "#64748b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>
            {subtitle}
          </small>
        )}
        {(!isAbsolute || durationMins >= 65) && <em>{eventDuration(item.startAt, item.endAt)}</em>}
      </button>
    );
  }

  if (isExamCard) {
    return (
      <button
        type="button"
        className="calendar-event"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "flex-start",
          overflow: "hidden",
          borderRadius: "8px",
          padding: isAbsolute ? "6px 8px" : "9px 10px 24px",
          textAlign: "left",
          transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
          background: "linear-gradient(135deg, #fff5f5 0%, #fff0f0 100%)",
          border: "1px solid #fee2e2",
          borderLeft: "4px solid #ef4444",
          color: "#991b1b",
          position: "relative",
          width: isAbsolute ? "100%" : "auto",
          height: isAbsolute ? "100%" : "auto",
          boxShadow: "0 3px 6px rgba(239, 68, 68, 0.06)"
        }}
        onClick={() => onSelect({ ...item, color: "pink" })}
      >
        <span className="event-time" style={{ color: "#ef4444", fontWeight: 700, fontSize: "10px" }}>
          {item.displayStartTime || formatTime(item.startAt)} - {item.displayEndTime || formatTime(item.endAt)}
        </span>
        <small style={{ marginTop: "3px", fontSize: "10px", color: "#991b1b", fontWeight: 800, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>
          {courseName || "Môn học"}
        </small>
        {(!isAbsolute || durationMins >= 45) && (
          <div style={{ display: "flex", alignItems: "center", gap: "4px", backgroundColor: "#fee2e2", color: "#ef4444", padding: "1px 6px", borderRadius: "4px", fontSize: "9px", fontWeight: "bold", width: "fit-content", marginTop: "4px" }}>
            🚨 Lịch thi
          </div>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: "4px", marginTop: "4px", width: "100%", overflow: "hidden" }}>
          {(!isAbsolute || durationMins >= 50) && <AlertTriangle size={12} style={{ color: "#ef4444", flexShrink: 0 }} />}
          <strong style={{ fontSize: "12px", lineHeight: "1.2", fontWeight: "700", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%", color: "#7f1d1d" }}>
            {cardTitle}
          </strong>
        </div>
        {(!isAbsolute || durationMins >= 75) && (
          <small style={{ marginTop: "3px", fontSize: "11px", color: "#b91c1c", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>
            {isClass ? (item.classSectionTitle || subtitle) : (scopeLine || subtitle)}
          </small>
        )}
        {(!isAbsolute || durationMins >= 65) && <em>{eventDuration(item.startAt, item.endAt)}</em>}
      </button>
    );
  }

  const subColor = getSubjectColor(item.courseId || item.subjectId);

  if (isClass) {
    return (
      <button
        type="button"
        className="calendar-event task-event"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "flex-start",
          overflow: "hidden",
          borderRadius: "8px",
          padding: isAbsolute ? "6px 8px" : "9px 10px 24px",
          textAlign: "left",
          transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
          background: `linear-gradient(135deg, ${subColor.bg} 0%, #ffffff 100%)`,
          border: `1px solid ${subColor.border}`,
          borderLeft: `4px solid ${subColor.main}`,
          color: subColor.text,
          position: "relative",
          width: isAbsolute ? "100%" : "auto",
          height: isAbsolute ? "100%" : "auto",
          boxShadow: "0 3px 6px rgba(0,0,0,0.04)"
        }}
        onClick={() => onSelect({ ...item, color: "green" })}
      >
        <span className="event-time" style={{ color: subColor.main, fontWeight: 700, fontSize: "10px" }}>
          {item.displayStartTime || formatTime(item.startAt)} - {item.displayEndTime || formatTime(item.endAt)}
        </span>
        <small style={{ marginTop: "3px", fontSize: "10px", color: subColor.text, fontWeight: 850, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>
          {courseName || "Môn học"}
        </small>
        {(!isAbsolute || durationMins >= 45) && (
          <div style={{ display: "flex", alignItems: "center", gap: "4px", backgroundColor: "#ffffff", border: `1px solid ${subColor.border}`, color: subColor.main, padding: "1px 6px", borderRadius: "4px", fontSize: "9px", fontWeight: "bold", width: "fit-content", marginTop: "4px" }}>
            🏫 Lên lớp
          </div>
        )}
        <strong style={{ fontSize: "12px", lineHeight: "1.2", marginTop: "4px", color: subColor.text, fontWeight: "700", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>
          {cardTitle}
        </strong>
        {(!isAbsolute || durationMins >= 75) && (
          <small style={{ marginTop: "3px", fontSize: "11px", color: subColor.text, opacity: 0.8, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>
            {item.classSectionTitle || subtitle}
          </small>
        )}
        {(!isAbsolute || durationMins >= 65) && <em>{eventDuration(item.startAt, item.endAt)}</em>}
      </button>
    );
  }

  // Self-study tasks (isTask)
  const isDone = item.status === "done";
  const isMissed = item.status === "missed";
  
  let bgStyle = `linear-gradient(135deg, ${subColor.bg} 0%, #ffffff 100%)`;
  let borderStyle = `1px solid ${subColor.border}`;
  let borderLeftStyle = `4px solid ${subColor.main}`;
  let textColor = subColor.text;
  let timeColor = subColor.main;
  let labelBg = "#ffffff";
  let opacityStyle = 1.0;
  
  if (isDone) {
    opacityStyle = 0.7;
    labelBg = "#f0fdf4";
    timeColor = "#10b981";
  } else if (isMissed) {
    labelBg = "#fef2f2";
    timeColor = "#ef4444";
  }

  return (
    <button
      type="button"
      className="calendar-event task-event"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        justifyContent: "flex-start",
        overflow: "hidden",
        borderRadius: "8px",
        padding: isAbsolute ? "6px 8px" : "9px 10px 24px",
        textAlign: "left",
        transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
        background: bgStyle,
        border: borderStyle,
        borderLeft: borderLeftStyle,
        color: textColor,
        opacity: opacityStyle,
        position: "relative",
        width: isAbsolute ? "100%" : "auto",
        height: isAbsolute ? "100%" : "auto",
        boxShadow: isMissed ? "0 3px 8px rgba(239, 68, 68, 0.08)" : "0 3px 6px rgba(0,0,0,0.04)"
      }}
      onClick={() => onSelect({ ...item, color: isDone ? "green" : isMissed ? "pink" : "green" })}
    >
      <span className="event-time" style={{ color: timeColor, fontWeight: 700, fontSize: "10px" }}>
        {item.displayStartTime || formatTime(item.startAt)} - {item.displayEndTime || formatTime(item.endAt)}
      </span>
      <small style={{ marginTop: "3px", fontSize: "10px", color: textColor, fontWeight: 850, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>
        {courseName || "Môn học"}
      </small>
      {(!isAbsolute || durationMins >= 45) && (
        <div style={{ display: "flex", alignItems: "center", gap: "4px", backgroundColor: labelBg, border: isDone ? "1px solid #bbf7d0" : isMissed ? "1px solid #fecaca" : `1px solid ${subColor.border}`, color: timeColor, padding: "1px 6px", borderRadius: "4px", fontSize: "9px", fontWeight: "bold", width: "fit-content", marginTop: "4px" }}>
          {isDone ? "✅ Đã học" : isMissed ? "⚠️ Trễ hạn" : `✏️ ${taskTypeLabels[item.type] || "Tự học"}`}
        </div>
      )}
      <strong style={{ fontSize: "12px", lineHeight: "1.2", marginTop: "4px", color: textColor, fontWeight: "700", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>
        {cardTitle}
      </strong>
      {(!isAbsolute || durationMins >= 75) && (
        <small style={{ marginTop: "3px", fontSize: "11px", color: textColor, opacity: 0.8, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>
          {scopeLine || subtitle}
        </small>
      )}
      {(!isAbsolute || durationMins >= 75) && masteryRows.length ? (
        <div className="event-mastery-strip" aria-label="Mastery" style={{ marginTop: "4px" }}>
          {masteryRows.slice(0, 1).map((row) => (
            <span key={`${row.kind}-${row.id}`} style={{ fontSize: "9px", backgroundColor: "rgba(255, 255, 255, 0.7)", border: isDone ? "1px solid #bbf7d0" : isMissed ? "1px solid #fecaca" : `1px solid ${subColor.border}`, color: timeColor, borderRadius: "999px", padding: "1px 6px" }}>{row.label} {formatPercent(row.masteryPercent)}</span>
          ))}
        </div>
      ) : null}
      {(!isAbsolute || durationMins >= 65) && <em style={{ color: timeColor, opacity: 0.8 }}>{eventDuration(item.startAt, item.endAt)}</em>}
      {isDone && (
        <div 
          title="Đã học xong"
          style={{
            position: "absolute",
            top: "6px",
            right: "6px",
            backgroundColor: "#10b981",
            color: "#ffffff",
            width: "16px",
            height: "16px",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "10px",
            fontWeight: "bold",
            boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
            zIndex: 10
          }}
        >
          ✓
        </div>
      )}
      {isMissed && (
        <div 
          title="Trễ hạn"
          style={{
            position: "absolute",
            top: "6px",
            right: "6px",
            backgroundColor: "#ef4444",
            color: "#ffffff",
            width: "16px",
            height: "16px",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "10px",
            fontWeight: "bold",
            boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
            zIndex: 10
          }}
        >
          !
        </div>
      )}
    </button>
  );
}

function taskActionLabel(type) {
  if (type === "new" || type === "preview") return "Học";
  if (type === "quiz") return "Quiz";
  return "Review";
}

function taskScopeLine(item) {
  const scopeItems = Array.isArray(item.scopeItems) ? item.scopeItems : [];
  if (scopeItems.length) {
    return scopeItems.map((scope) => scope.title).filter(Boolean).join("; ");
  }
  return item.lessonTitle || "";
}

function taskMasteryRows(item) {
  const rows = [];
  if (item.topicStats?.title) {
    rows.push({
      id: item.topicStats.id || item.topicId || "topic",
      kind: "topic",
      label: "Topic",
      title: item.topicStats.title,
      masteryPercent: item.topicStats.masteryPercent ?? item.topicStats.overallMasteryPercent,
      confidencePercent: item.topicStats.confidencePercent,
      scopeHint: topicScopeHint(item.topicStats)
    });
  }
  const scopeItems = Array.isArray(item.scopeItems) ? item.scopeItems : [];
  scopeItems.forEach((scope, index) => {
    rows.push({
      id: scope.id || `scope-${index}`,
      kind: "subtopic",
      label: "Subtopic",
      title: scope.title,
      masteryPercent: scope.masteryPercent,
      confidencePercent: scope.confidencePercent,
      scopeHint: scope.startsOn ? `Học trên trường: ${String(scope.startsOn).slice(0, 10)}` : ""
    });
  });
  return rows;
}

function topicScopeHint(stats) {
  const total = Number(stats?.totalSubtopicCount || 0);
  const available = Number(stats?.availableSubtopicCount || 0);
  if (!total) return "";
  return available >= total ? `Đã học ${total}/${total} mục` : `Đã học ${available}/${total} mục`;
}

function formatPercent(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${Math.round(numeric)}%` : "--";
}

function MiniCalendar({ weekStart, tasks = [], academicEvents = [], onWeekStartChange }) {
  const [currentViewDate, setCurrentViewDate] = useState(() => new Date(weekStart));

  useEffect(() => {
    setCurrentViewDate(new Date(weekStart));
  }, [weekStart]);

  const handlePrevMonth = () => {
    setCurrentViewDate((prev) => {
      const copy = new Date(prev);
      copy.setMonth(copy.getMonth() - 1);
      return copy;
    });
  };

  const handleNextMonth = () => {
    setCurrentViewDate((prev) => {
      const copy = new Date(prev);
      copy.setMonth(copy.getMonth() + 1);
      return copy;
    });
  };

  const monthDays = useMemo(() => {
    const startOfMonth = new Date(currentViewDate.getFullYear(), currentViewDate.getMonth(), 1);
    const day = startOfMonth.getDay() || 7;
    const startOfGrid = new Date(startOfMonth);
    startOfGrid.setDate(startOfGrid.getDate() - day + 1);
    return Array.from({ length: 35 }, (_, index) => addDays(startOfGrid, index));
  }, [currentViewDate]);

  return (
    <Card className="mini-calendar">
      <div className="mini-calendar-head">
        <strong>{currentViewDate.toLocaleDateString("vi-VN", { month: "long", year: "numeric" })}</strong>
        <span style={{ display: "flex", gap: "6px" }}>
          <IconButton icon={ChevronLeft} label="Tháng trước" onClick={handlePrevMonth} style={{ padding: "2px" }} />
          <IconButton icon={ChevronRight} label="Tháng sau" onClick={handleNextMonth} style={{ padding: "2px" }} />
        </span>
      </div>
      <div className="mini-weekdays">{["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((d) => <span key={d}>{d}</span>)}</div>
      <div className="mini-days">
        {monthDays.map((date) => {
          const dateKey = formatDateKey(date);
          const isToday = date.toDateString() === new Date().toDateString();
          const isSelectedWeek = startOfWeek(date).toDateString() === weekStart.toDateString();
          const isCurrentMonth = date.getMonth() === currentViewDate.getMonth();
          
          const hasExam = academicEvents.some((item) => {
            const itemDate = (item.segmentDateKey || formatDateKey(item.startAt));
            const isExamItem = item.itemKind === "exam" || 
              (item.type === "diagnostic" || item.type === "mock_test") ||
              (typeof item.title === "string" && (item.title.includes("Thi") || item.title.toLowerCase().includes("exam"))) ||
              (typeof item.lessonTitle === "string" && (item.lessonTitle.includes("Thi") || item.lessonTitle.toLowerCase().includes("exam")));
            return isExamItem && itemDate === dateKey;
          });
          
          const hasTask = tasks.some((item) => {
            const itemDate = (item.segmentDateKey || formatDateKey(item.startAt));
            return itemDate === dateKey;
          });

          return (
            <button
              key={dateKey}
              onClick={() => onWeekStartChange && onWeekStartChange(startOfWeek(date))}
              style={{
                background: "transparent",
                border: "none",
                padding: 0,
                cursor: "pointer",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                position: "relative"
              }}
            >
              <span
                className={`${isToday ? "active" : ""} ${!isCurrentMonth ? "muted" : ""}`}
                style={{
                  border: isSelectedWeek && !isToday ? "1px solid var(--brand-green-strong)" : "none",
                  fontWeight: isSelectedWeek ? "bold" : "normal"
                }}
              >
                {date.getDate()}
              </span>
              <div
                style={{
                  display: "flex",
                  gap: "2px",
                  justifyContent: "center",
                  position: "absolute",
                  bottom: "-2px"
                }}
              >
                {hasExam && (
                  <span
                    style={{
                      width: "4px",
                      height: "4px",
                      borderRadius: "50%",
                      backgroundColor: "#ef4444"
                    }}
                    title="Lịch thi"
                  />
                )}
                {hasTask && !hasExam && (
                  <span
                    style={{
                      width: "4px",
                      height: "4px",
                      borderRadius: "50%",
                      backgroundColor: "#78d20c"
                    }}
                    title="Nhiệm vụ học"
                  />
                )}
              </div>
            </button>
          );
        })}
      </div>
    </Card>
  );
}

export function LeftPanel({
  courses,
  missedCount,
  busyCount,
  examCount = 0,
  classCount = 0,
  onCreateTask,
  onCreateBusyEvent,
  onReschedule,
  tasks = [],
  academicEvents = [],
  selectedCourseIds,
  setSelectedCourseIds,
  showTasks,
  setShowTasks,
  showClass,
  setShowClass,
  showExam,
  setShowExam,
  showBusy,
  setShowBusy,
  weekStart,
  onWeekStartChange
}) {
  const onToggleCourse = (courseId) => {
    setSelectedCourseIds((prev) => {
      const next = new Set(prev);
      if (next.has(courseId)) {
        next.delete(courseId);
      } else {
        next.add(courseId);
      }
      return next;
    });
  };

  return (
    <aside className="calendar-left-panel">
      <Button variant="primary" icon={CalendarPlus} className="full-btn" onClick={onCreateBusyEvent}>Tạo sự kiện bận</Button>
      <Button variant="secondary" icon={Plus} className="full-btn" onClick={onCreateTask}>Tạo nhiệm vụ học</Button>
      <MiniCalendar
        weekStart={weekStart}
        tasks={tasks}
        academicEvents={academicEvents}
        onWeekStartChange={onWeekStartChange}
      />
      <Card 
        className="calendar-alert"
        style={missedCount > 0 ? {
          background: "linear-gradient(135deg, #fff5f5 0%, #fff0f0 100%)",
          border: "1px solid #fee2e2",
          borderLeft: "4px solid #ef4444",
          boxShadow: "0 4px 12px rgba(239, 68, 68, 0.08)"
        } : {}}
      >
        <AlertTriangle size={18} style={missedCount > 0 ? { color: "#ef4444" } : {}} />
        <strong style={missedCount > 0 ? { color: "#991b1b" } : {}}>
          {missedCount > 0 ? "Phát hiện nhiệm vụ trễ hạn!" : "Cần chú ý"}
        </strong>
        <p style={missedCount > 0 ? { color: "#7f1d1d", fontSize: "13px" } : {}}>
          {missedCount > 0 
            ? `Bạn đang bỏ lỡ ${missedCount} nhiệm vụ học tập! Vui lòng lập lại lịch để phân bổ lại thời gian học tối ưu.` 
            : `Có ${missedCount} nhiệm vụ trễ, ${busyCount} sự kiện bận, ${classCount} buổi học và ${examCount} lịch thi trong tuần.`
          }
        </p>
        <Button 
          variant={missedCount > 0 ? "primary" : "secondary"} 
          size="sm" 
          icon={RotateCcw} 
          onClick={onReschedule}
          style={missedCount > 0 ? {
            backgroundColor: "#ef4444",
            borderColor: "#ef4444",
            color: "#ffffff",
            fontWeight: "700"
          } : {}}
        >
          Lập lại lịch ngay
        </Button>
      </Card>
      
      <div className="calendar-checks">
        <h3>Lịch của tôi</h3>
        {courses.map((course) => {
          const colorObj = getSubjectColor(course.id);
          const isSelected = selectedCourseIds.has(course.id);
          return (
            <button
              key={course.id}
              onClick={() => onToggleCourse(course.id)}
              className={`check-pill ${isSelected ? "checked" : ""}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "9px",
                color: isSelected ? "#1f2937" : "#4b5563",
                fontSize: "14px",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                padding: "6px 0",
                textAlign: "left",
                width: "100%",
                transition: "all 0.15s ease"
              }}
            >
              <Check
                size={14}
                style={{
                  display: "inline-flex",
                  width: "20px",
                  height: "20px",
                  flex: "0 0 auto",
                  borderRadius: "6px",
                  padding: "3px",
                  backgroundColor: isSelected ? colorObj.bg : "#fff",
                  borderColor: isSelected ? colorObj.border : "var(--surface-line)",
                  borderWidth: "1px",
                  borderStyle: "solid",
                  color: isSelected ? colorObj.main : "transparent",
                  transition: "all 0.15s ease"
                }}
              />
              <span style={{ fontWeight: isSelected ? 600 : 500, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {course.name}
              </span>
            </button>
          );
        })}
      </div>

      <div className="calendar-checks" style={{ marginTop: "14px" }}>
        <h3>Loại sự kiện</h3>
        
        {/* Lịch học theo topic */}
        <button
          onClick={() => setShowTasks(!showTasks)}
          className={`check-pill ${showTasks ? "checked" : ""}`}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "9px",
            color: showTasks ? "#1f2937" : "#4b5563",
            fontSize: "14px",
            background: "transparent",
            border: "none",
            cursor: "pointer",
            padding: "6px 0",
            textAlign: "left",
            width: "100%",
            transition: "all 0.15s ease"
          }}
        >
          <Check
            size={14}
            style={{
              display: "inline-flex",
              width: "20px",
              height: "20px",
              flex: "0 0 auto",
              borderRadius: "6px",
              padding: "3px",
              backgroundColor: showTasks ? "#f1f5f9" : "#fff",
              borderColor: showTasks ? "#cbd5e1" : "var(--surface-line)",
              borderWidth: "1px",
              borderStyle: "solid",
              color: showTasks ? "#475569" : "transparent",
              transition: "all 0.15s ease"
            }}
          />
          <span style={{ fontWeight: showTasks ? 600 : 500 }}>
            ✏️ Tự học
          </span>
        </button>

        {/* Lịch học trường */}
        <button
          onClick={() => setShowClass(!showClass)}
          className={`check-pill ${showClass ? "checked" : ""}`}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "9px",
            color: showClass ? "#1f2937" : "#4b5563",
            fontSize: "14px",
            background: "transparent",
            border: "none",
            cursor: "pointer",
            padding: "6px 0",
            textAlign: "left",
            width: "100%",
            transition: "all 0.15s ease"
          }}
        >
          <Check
            size={14}
            style={{
              display: "inline-flex",
              width: "20px",
              height: "20px",
              flex: "0 0 auto",
              borderRadius: "6px",
              padding: "3px",
              backgroundColor: showClass ? "#eff6ff" : "#fff",
              borderColor: showClass ? "#3b82f6" : "var(--surface-line)",
              borderWidth: "1px",
              borderStyle: "solid",
              color: showClass ? "#3b82f6" : "transparent",
              transition: "all 0.15s ease"
            }}
          />
          <span style={{ fontWeight: showClass ? 600 : 500 }}>
            🏫 Lên lớp
          </span>
        </button>

        {/* Lịch thi */}
        <button
          onClick={() => setShowExam(!showExam)}
          className={`check-pill ${showExam ? "checked" : ""}`}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "9px",
            color: showExam ? "#1f2937" : "#4b5563",
            fontSize: "14px",
            background: "transparent",
            border: "none",
            cursor: "pointer",
            padding: "6px 0",
            textAlign: "left",
            width: "100%",
            transition: "all 0.15s ease"
          }}
        >
          <Check
            size={14}
            style={{
              display: "inline-flex",
              width: "20px",
              height: "20px",
              flex: "0 0 auto",
              borderRadius: "6px",
              padding: "3px",
              backgroundColor: showExam ? "#fef2f2" : "#fff",
              borderColor: showExam ? "#fecaca" : "var(--surface-line)",
              borderWidth: "1px",
              borderStyle: "solid",
              color: showExam ? "#ef4444" : "transparent",
              transition: "all 0.15s ease"
            }}
          />
          <span style={{ fontWeight: showExam ? 600 : 500 }}>
            🚨 Lịch thi
          </span>
        </button>

        {/* Sự kiện bận */}
        <button
          onClick={() => setShowBusy(!showBusy)}
          className={`check-pill ${showBusy ? "checked" : ""}`}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "9px",
            color: showBusy ? "#1f2937" : "#4b5563",
            fontSize: "14px",
            background: "transparent",
            border: "none",
            cursor: "pointer",
            padding: "6px 0",
            textAlign: "left",
            width: "100%",
            transition: "all 0.15s ease"
          }}
        >
          <Check
            size={14}
            style={{
              display: "inline-flex",
              width: "20px",
              height: "20px",
              flex: "0 0 auto",
              borderRadius: "6px",
              padding: "3px",
              backgroundColor: showBusy ? "#f1f5f9" : "#fff",
              borderColor: showBusy ? "#cbd5e1" : "var(--surface-line)",
              borderWidth: "1px",
              borderStyle: "solid",
              color: showBusy ? "#64748b" : "transparent",
              transition: "all 0.15s ease"
            }}
          />
          <span style={{ fontWeight: showBusy ? 600 : 500 }}>
            🚫 Bận
          </span>
        </button>
      </div>
    </aside>
  );
}

export function RescheduleModal({ open, courses, missedCount = 0, busy = false, onClose, onSubmit }) {
  const [allCourses, setAllCourses] = useState(true);
  const [selectedCourseIds, setSelectedCourseIds] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setAllCourses(true);
    setSelectedCourseIds(courses.map((course) => course.id));
    setError("");
  }, [open, courses]);

  const toggleCourse = (courseId) => {
    setAllCourses(false);
    setSelectedCourseIds((current) => (
      current.includes(courseId)
        ? current.filter((id) => id !== courseId)
        : [...current, courseId]
    ));
  };

  const submit = async () => {
    setError("");
    const courseIds = allCourses ? courses.map((course) => course.id) : selectedCourseIds;
    if (!courseIds.length) {
      setError("Chọn ít nhất một môn để lập lại lịch.");
      return;
    }
    try {
      await onSubmit({ allCourses, courseIds });
    } catch (err) {
      setError(err.message || "Không thể lập lại lịch.");
    }
  };

  return (
    <Modal
      title="Lập lại lịch"
      open={open}
      onClose={busy ? undefined : onClose}
      className="reschedule-modal"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Hủy</Button>
          <Button variant="primary" icon={RotateCcw} onClick={submit} disabled={busy || !courses.length}>{busy ? "Đang lập lại..." : "Lập lại lịch"}</Button>
        </>
      }
    >
      <div className="form-grid">
        {error ? <div className="form-error">{error}</div> : null}
        <p className="reschedule-copy">
          Lịch mới sẽ dùng lịch bận/rảnh hiện tại và mastery mới nhất. {missedCount ? `Có ${missedCount} nhiệm vụ trễ trong tuần này.` : "Không có nhiệm vụ trễ trong tuần này."}
        </p>
        <label className="checkbox-row reschedule-all-row">
          <input
            type="checkbox"
            checked={allCourses}
            onChange={(event) => {
              setAllCourses(event.target.checked);
              if (event.target.checked) setSelectedCourseIds(courses.map((course) => course.id));
            }}
            disabled={busy || !courses.length}
          />
          <span>Tất cả môn học</span>
        </label>
        <div className="reschedule-course-list" aria-label="Chọn môn học để lập lại lịch">
          {courses.length ? courses.map((course) => {
            const checked = allCourses || selectedCourseIds.includes(course.id);
            return (
              <label key={course.id} className="checkbox-row reschedule-course-row">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={busy || allCourses}
                  onChange={() => toggleCourse(course.id)}
                />
                <span>{course.name}</span>
                <small>{course.masteryPercent ?? 0}% mastery</small>
              </label>
            );
          }) : <div className="empty-day">Chưa có môn học</div>}
        </div>
      </div>
    </Modal>
  );
}

export function EventPopover({ event, courseById, quizzes = [], topics = [], syllabi = [], onClose, onEditBusy, onDeleteBusy }) {
  const [reviewOpen, setReviewOpen] = useState(false);
  const isBusy = event?.itemKind === "busy";
  const isAcademic = event?.itemKind === "exam" || event?.itemKind === "class";
  const isExam = event?.itemKind === "exam";
  const isTask = !isBusy && !isAcademic;

  const matchedQuiz = useMemo(() => {
    if (!event || isBusy || !event.courseId || !Array.isArray(quizzes)) return null;
    return quizzes.find((q) => {
      if (!q) return false;
      const qSubjectId = q.courseId || q.subjectId || q.subject_id;
      if (qSubjectId !== event.courseId) return false;
      if (isTask) {
        const tId = event.topicId || event.topic_id || event.subtopic_id || event.parent_topic_id;
        if (tId && (q.topicId === tId || q.topic_id === tId)) return true;
      }
      if (event.itemKind === "class" && event.lessonId) {
        if (!Array.isArray(topics)) return false;
        const lessonTopics = topics.filter(t => t && (t.lessonId === event.lessonId || t.lesson_id === event.lessonId));
        if (lessonTopics.some(t => t && (t.id === q.topicId || t.id === q.topic_id))) return true;
      }
      return false;
    });
  }, [event, quizzes, topics, isBusy, isTask]);

  if (!event) return null;

  const course = event.courseId && courseById && typeof courseById.get === "function" ? courseById.get(event.courseId) : null;
  const badgeTone = isBusy ? "blue" : event.color === "green" ? "green" : "blue";
  const editableEvent = event.originalStartAt ? { ...event, startAt: event.originalStartAt, endAt: event.originalEndAt } : event;
  const masteryRows = isTask ? taskMasteryRows(event) : [];
  const popoverTitle = isTask && event.topicStats?.title ? `${taskActionLabel(event.type)}: ${event.topicStats.title}` : event.title;
  const defaultReason = event.itemKind === "class"
    ? "System-suggested study block derived from the on-campus lesson."
    : (isBusy ? "Busy event." : "Study plan task.");

  const safeSyllabi = Array.isArray(syllabi) ? syllabi : [];
  const syllabusObj = safeSyllabi.find((s) => s && s.courseId === event.courseId);
  const syllabusStatus = syllabusObj?.syllabus?.status; // 'ready', 'processing', 'failed'

  const deleteBusyInstance = () => {
    if (window.confirm("Xóa riêng sự kiện này?")) {
      onDeleteBusy(event.id, false);
    }
  };

  const deleteBusySeries = () => {
    if (window.confirm("Xóa toàn bộ chuỗi sự kiện lặp lại này?")) {
      onDeleteBusy(event.id, true);
    }
  };

  return (
    <div className="event-popover-backdrop" onClick={onClose}>
      <Card className="event-popover" onClick={(clickEvent) => clickEvent.stopPropagation()}>
        <div className="event-popover-head">
          <div>
            <Badge tone={badgeTone}>{isBusy ? "Sự kiện bận" : (event.itemKind === "class" ? "System suggestion" : (taskTypeLabels[event.type] || event.type))}</Badge>
            <h3>{popoverTitle}</h3>
            <p>{isBusy ? "Khoảng thời gian không thể tham gia" : (course?.name || "Môn học")}</p>
          </div>
          <IconButton icon={X} label="Đóng" onClick={onClose} />
        </div>
        <div className="event-popover-body">
          <div className="event-detail-list">
            <span><Clock size={16} /> Từ {event.displayStartTime || formatTime(event.startAt)} đến {event.displayEndTime || formatTime(event.endAt)}</span>
            {event.itemKind === "class" && event.classChapterTitle ? (
              <span><FileText size={16} /> {"Chương"}: {event.classChapterTitle}</span>
            ) : null}
            {event.itemKind === "class" && event.lessonTitle ? (
              <span><FileText size={16} /> Bài học: {event.lessonTitle}</span>
            ) : null}
            <span><AlertTriangle size={16} /> {event.reason || defaultReason}</span>
            <span><FileText size={16} /> Trạng thái: {isBusy ? "Bận" : event.status === "done" ? "Đã hoàn thành" : event.status === "todo" ? "Chưa hoàn thành" : event.status === "missed" ? "Trễ" : event.status === "future" ? "Sắp tới" : event.status === "current" ? "Đang học" : event.status === "scheduled" ? "Sắp tới" : event.status === "ready" ? "Sẵn sàng" : event.status}</span>
            {!isBusy && !isExam && (
              <span>
                <HelpCircle size={16} /> Quiz học tập:{" "}
                {matchedQuiz ? (
                  <span style={{ color: "#10b981", fontWeight: 600 }}>Đã sẵn sàng</span>
                ) : syllabusStatus === "processing" ? (
                  <span style={{ color: "#f59e0b", fontWeight: 500 }}>Đang tạo quiz...</span>
                ) : (
                  <span style={{ color: "#6b7280" }}>Chưa có quiz</span>
                )}
              </span>
            )}
          </div>
          {masteryRows.length ? (
            <div className="task-scope-panel">
              <div className="task-scope-head">
                <strong>Phạm vi buổi này</strong>
                {event.topicStats?.scope ? <span>{event.topicStats.scope === "partial_topic" ? "Một phần topic" : "Cả topic"}</span> : null}
              </div>
              <div className="task-mastery-rows">
                {masteryRows.map((row) => (
                  <div key={`${row.kind}-${row.id}`} className={`task-mastery-row ${row.kind}`}>
                    <span>{row.label}</span>
                    <strong>{row.title}</strong>
                    <em>{formatPercent(row.masteryPercent)} mastery</em>
                    {row.scopeHint ? <small>{row.scopeHint}</small> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <div className="event-popover-actions">
          {isBusy ? (
            <>
              <Button variant="primary" icon={Edit3} onClick={() => onEditBusy(editableEvent)}>Sửa sự kiện</Button>
              {event.recurrenceId ? (
                <>
                  <Button variant="secondary" icon={Trash2} onClick={deleteBusyInstance}>Xóa lần này</Button>
                  <Button variant="secondary" icon={Trash2} className="btn-danger" onClick={deleteBusySeries}>Xóa cả chuỗi</Button>
                </>
              ) : (
                <Button variant="secondary" icon={Trash2} onClick={deleteBusyInstance}>Xóa</Button>
              )}
            </>
          ) : isAcademic ? (
            <>
              <Button variant="primary" onClick={() => navigate(`/courses/detail/${event.courseId}`)}>Xem môn</Button>
              {matchedQuiz && (
                <Button variant="secondary" icon={HelpCircle} onClick={() => setReviewOpen(true)}>Xem câu hỏi ôn tập</Button>
              )}
            </>
          ) : (
            <>
              <Button variant="primary" icon={Play} onClick={() => navigate(`/study/${event.courseId}?task=${event.id}`)}>Bắt đầu học</Button>
              {matchedQuiz && (
                <Button variant="secondary" icon={HelpCircle} onClick={() => setReviewOpen(true)}>Xem câu hỏi ôn tập</Button>
              )}
              <Button variant="ghost" onClick={() => navigate(`/courses/detail/${event.courseId}`)}>Xem môn</Button>
            </>
          )}
          <Button variant="secondary" onClick={onClose}>Đóng</Button>
        </div>
      </Card>
      {matchedQuiz && reviewOpen && (
        <ReviewQuizModal open={reviewOpen} onClose={() => setReviewOpen(false)} quiz={matchedQuiz} />
      )}
    </div>
  );
}

export function ReviewQuizModal({ open, onClose, quiz }) {
  if (!open || !quiz) return null;
  const questions = Array.isArray(quiz.questions) ? quiz.questions.slice(0, 5) : [];
  return (
    <Modal
      title={`Xem câu hỏi ôn tập: ${quiz.title}`}
      open={open}
      onClose={onClose}
      className="review-quiz-modal"
      footer={<Button variant="primary" onClick={onClose}>Đóng</Button>}
    >
      <div className="review-quiz-container" style={{ maxHeight: "60vh", overflowY: "auto", padding: "0 8px" }}>
        {questions.map((q, idx) => {
          if (!q) return null;
          return (
            <div key={q.id || idx} style={{ marginBottom: "16px", borderBottom: "1px solid var(--surface-line)", paddingBottom: "12px" }}>
              <h4 style={{ fontWeight: 500, fontSize: "15px", lineHeight: "1.5", color: "var(--text-main)", margin: 0 }}>
                Câu {idx + 1}: {q.question}
              </h4>
            </div>
          );
        })}
      </div>
    </Modal>
  );
}

export function CreateTaskModal({ open, courses, onClose, onCreate }) {
  const [form, setForm] = useState({ title: "", courseId: "", type: "quiz", date: formatDateInput(new Date()), start: "18:00", end: "18:30", reason: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    if (open && courses[0] && !form.courseId) setForm((current) => ({ ...current, courseId: courses[0].id }));
  }, [open, courses, form.courseId]);

  const submit = async () => {
    setError("");
    if (!form.title.trim()) {
      setError("Vui lòng nhập tiêu đề.");
      return;
    }
    if (!form.courseId) {
      setError("Vui lòng chọn môn học.");
      return;
    }
    const startAt = new Date(`${form.date}T${form.start}:00`);
    const endAt = new Date(`${form.date}T${form.end}:00`);
    if (endAt <= startAt) {
      setError("Thời gian kết thúc phải sau thời gian bắt đầu.");
      return;
    }
    try {
      await onCreate({
        courseId: form.courseId,
        title: form.title.trim(),
        type: form.type,
        startAt: startAt.toISOString(),
        endAt: endAt.toISOString(),
        priority: "medium",
        reason: form.reason || "Tạo thủ công từ lịch học."
      });
    } catch (err) {
      setError(err.message || "Không thể lưu nhiệm vụ.");
    }
  };

  return (
    <Modal title="Tạo nhiệm vụ học" open={open} onClose={onClose} footer={<><Button variant="secondary" onClick={onClose}>Hủy</Button><Button variant="primary" onClick={submit}>Lưu nhiệm vụ</Button></>}>
      <div className="form-grid">
        {error ? <div className="form-error">{error}</div> : null}
        <label><span>Tiêu đề</span><input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Trắc nghiệm: Không gian vectơ" /></label>
        <label>
          <span>Môn học</span>
          <select value={form.courseId} onChange={(event) => setForm({ ...form, courseId: event.target.value })}>
            {courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}
          </select>
        </label>
        <label>
          <span>Loại nhiệm vụ</span>
          <select value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })}>
            {Object.entries(taskTypeLabels).filter(([value]) => value !== "busy").map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>
          <span>Thời gian</span>
          <div className="inline-inputs">
            <input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} />
            <input type="time" value={form.start} onChange={(event) => setForm({ ...form, start: event.target.value })} />
            <input type="time" value={form.end} onChange={(event) => setForm({ ...form, end: event.target.value })} />
          </div>
        </label>
        <label><span>Lý do / ghi chú</span><textarea value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} rows="3" /></label>
      </div>
    </Modal>
  );
}

export function CreateBusyEventModal({ open, event, onClose, onCreate }) {
  const [form, setForm] = useState({
    title: "Bận",
    startDate: formatDateInput(new Date()),
    startTime: "09:00",
    endDate: formatDateInput(new Date()),
    endTime: "10:00",
    reason: "",
    repeatType: "none",
    untilDate: formatDateInput(addDays(new Date(), 21)),
    customRecurrence: null
  });
  const [error, setError] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [showCustomModal, setShowCustomModal] = useState(false);

  const recurrenceLabels = useMemo(() => {
    const weekdaysVi = ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];
    const ordinalNamesVi = ["đầu tiên", "thứ hai", "thứ ba", "thứ tư", "thứ năm"];
    const monthsVi = [
      "tháng 1", "tháng 2", "tháng 3", "tháng 4", "tháng 5", "tháng 6",
      "tháng 7", "tháng 8", "tháng 9", "tháng 10", "tháng 11", "tháng 12"
    ];
    if (!form.startDate) {
      return { weekdayName: "Thứ Hai", ordinalName: "đầu tiên", day: 1, monthName: "tháng 1" };
    }
    const parts = form.startDate.split("-");
    const dateObj = new Date(parts[0], parts[1] - 1, parts[2]);
    const dayOfWeekIndex = dateObj.getDay();
    const weekdayName = weekdaysVi[dayOfWeekIndex];
    
    const dayOfMonth = dateObj.getDate();
    const ordinalIndex = Math.ceil(dayOfMonth / 7) - 1;
    const ordinalName = ordinalNamesVi[ordinalIndex] || "thứ năm";
    
    const monthName = monthsVi[dateObj.getMonth()];
    return { weekdayName, ordinalName, day: dayOfMonth, monthName };
  }, [form.startDate]);

  const formatCustomLabel = (custom) => {
    if (!custom) return "Tùy chỉnh...";
    const { frequency, interval, byDay, count, untilDate } = custom;
    const unit = frequency.replace("custom_", "");
    
    let unitLabel = "";
    if (unit === "daily") unitLabel = "ngày";
    else if (unit === "weekly") unitLabel = "tuần";
    else if (unit === "monthly") unitLabel = "tháng";
    else if (unit === "yearly") unitLabel = "năm";
    
    let base = `Mỗi ${interval} ${unitLabel}`;
    
    if (unit === "weekly" && byDay && byDay.length > 0) {
      const fullDayMap = {
        Mon: "Thứ Hai", Tue: "Thứ Ba", Wed: "Thứ Tư", Thu: "Thứ Năm",
        Fri: "Thứ Sáu", Sat: "Thứ Bảy", Sun: "Chủ Nhật"
      };
      const daysStr = byDay.map(d => fullDayMap[d] || d).join(", ");
      base = `${base} vào ${daysStr}`;
    }
    
    if (untilDate) {
      base = `${base}, đến ngày ${untilDate}`;
    } else if (count) {
      base = `${base}, ${count} lần`;
    }
    
    return base;
  };

  const getRepeatLabel = (value) => {
    if (value.startsWith("custom_")) {
      return formatCustomLabel(form.customRecurrence);
    }
    switch (value) {
      case "none":
        return "Không lặp lại";
      case "daily":
        return "Hàng ngày";
      case "weekly":
        return `Hàng tuần vào ${recurrenceLabels.weekdayName}`;
      case "monthly":
        return `Hàng tháng vào ngày ${recurrenceLabels.weekdayName} ${recurrenceLabels.ordinalName}`;
      case "annually":
        return `Hàng năm vào ngày ${recurrenceLabels.day} ${recurrenceLabels.monthName}`;
      case "every_weekday":
        return "Mỗi ngày trong tuần (từ Thứ Hai đến Thứ Sáu)";
      case "custom":
        return "Tùy chỉnh...";
      default:
        return "Không lặp lại";
    }
  };

  useEffect(() => {
    if (!dropdownOpen) return;
    const handleOutsideClick = (e) => {
      if (!e.target.closest(".custom-select-container")) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [dropdownOpen]);

  useEffect(() => {
    if (!open) return;
    setDropdownOpen(false);
    setShowCustomModal(false);
    if (event) {
      setForm({
        title: event.title || "Bận",
        startDate: formatDateInput(event.startAt),
        startTime: toTimeInput(event.startAt),
        endDate: formatDateInput(event.endAt),
        endTime: toTimeInput(event.endAt),
        reason: event.reason || "",
        repeatType: "none",
        untilDate: formatDateInput(addDays(new Date(), 21)),
        customRecurrence: null
      });
    } else {
      setForm({
        title: "Bận",
        startDate: formatDateInput(new Date()),
        startTime: "09:00",
        endDate: formatDateInput(new Date()),
        endTime: "10:00",
        reason: "",
        repeatType: "none",
        untilDate: formatDateInput(addDays(new Date(), 21)),
        customRecurrence: null
      });
    }
    setError("");
  }, [open, event]);

  const submit = async () => {
    setError("");
    if (!form.title.trim()) {
      setError("Vui lòng nhập tiêu đề.");
      return;
    }
    const startAt = new Date(`${form.startDate}T${form.startTime}:00`);
    const endAt = new Date(`${form.endDate}T${form.endTime}:00`);
    if (endAt <= startAt) {
      setError("Thời gian kết thúc phải sau thời gian bắt đầu.");
      return;
    }
    const payload = {
      title: form.title.trim(),
      startAt: startAt.toISOString(),
      endAt: endAt.toISOString(),
      reason: form.reason.trim()
    };
    if (form.repeatType.startsWith("custom_")) {
      const custom = form.customRecurrence;
      payload.recurrence = {
        frequency: form.repeatType,
        interval: custom.interval,
        byDay: custom.byDay,
        count: custom.count,
        untilDate: custom.untilDate
      };
    } else if (form.repeatType !== "none" && form.repeatType !== "custom") {
      payload.recurrence = {
        frequency: form.repeatType,
        untilDate: form.untilDate
      };
    }
    try {
      await onCreate(payload);
    } catch (err) {
      setError(err.message || "Không thể lưu sự kiện bận.");
    }
  };

  return (
    <>
      <Modal title={event ? "Sửa event bận" : "Tạo event bận"} open={open} onClose={onClose} footer={<><Button variant="secondary" onClick={onClose}>Hủy</Button><Button variant="primary" icon={Ban} onClick={submit}>Lưu event</Button></>}>
        <div className="form-grid">
          {error ? <div className="form-error">{error}</div> : null}
          <label><span>Tiêu đề</span><input value={form.title} onChange={(inputEvent) => setForm({ ...form, title: inputEvent.target.value })} placeholder="Không thể tham gia" /></label>
          <label>
            <span>Bắt đầu</span>
            <div className="inline-inputs">
              <input type="date" value={form.startDate} onChange={(inputEvent) => setForm({ ...form, startDate: inputEvent.target.value })} />
              <input type="time" value={form.startTime} onChange={(inputEvent) => setForm({ ...form, startTime: inputEvent.target.value })} />
            </div>
          </label>
          <label>
            <span>Kết thúc</span>
            <div className="inline-inputs">
              <input type="date" value={form.endDate} onChange={(inputEvent) => setForm({ ...form, endDate: inputEvent.target.value })} />
              <input type="time" value={form.endTime} onChange={(inputEvent) => setForm({ ...form, endTime: inputEvent.target.value })} />
            </div>
          </label>
          <div className="field custom-select-container">
            <span>Lặp lại</span>
            <button
              type="button"
              className={`google-calendar-select-trigger ${dropdownOpen ? "active" : ""}`}
              onClick={() => setDropdownOpen(!dropdownOpen)}
            >
              <span>{getRepeatLabel(form.repeatType)}</span>
              <span className="arrow-icon">{dropdownOpen ? "▲" : "▼"}</span>
            </button>

            {dropdownOpen && (
              <div className="google-calendar-dropdown-menu">
                {[
                  { value: "none", label: "Không lặp lại" },
                  { value: "daily", label: "Hàng ngày" },
                  { value: "weekly", label: `Hàng tuần vào ${recurrenceLabels.weekdayName}` },
                  { value: "monthly", label: `Hàng tháng vào ngày ${recurrenceLabels.weekdayName} ${recurrenceLabels.ordinalName}` },
                  { value: "annually", label: `Hàng năm vào ngày ${recurrenceLabels.day} ${recurrenceLabels.monthName}` },
                  { value: "every_weekday", label: "Mỗi ngày trong tuần (từ Thứ Hai đến Thứ Sáu)" },
                  { value: "custom", label: "Tùy chỉnh..." }
                ].map((opt) => {
                  let displayLabel = opt.label;
                  if (opt.value === "annually") {
                    displayLabel = `Hàng năm vào ngày ${recurrenceLabels.day} ${recurrenceLabels.monthName}`;
                  }
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      className={`google-calendar-dropdown-item ${form.repeatType === opt.value ? "selected" : ""}`}
                      onClick={() => {
                        if (opt.value === "custom") {
                          setDropdownOpen(false);
                          setShowCustomModal(true);
                        } else {
                          setForm({ ...form, repeatType: opt.value });
                          setDropdownOpen(false);
                        }
                      }}
                    >
                      {displayLabel}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          {form.repeatType !== "none" && form.repeatType !== "custom" && !form.repeatType.startsWith("custom_") && (
            <label>
              <span>Lặp lại đến hết ngày</span>
              <input type="date" value={form.untilDate} onChange={(inputEvent) => setForm({ ...form, untilDate: inputEvent.target.value })} />
            </label>
          )}
          <label><span>Ghi chú</span><textarea value={form.reason} onChange={(inputEvent) => setForm({ ...form, reason: inputEvent.target.value })} rows="3" placeholder="Phỏng vấn, di chuyển, meeting..." /></label>
        </div>
      </Modal>

      {showCustomModal && (
        <CustomRecurrenceModal
          open={showCustomModal}
          onClose={() => setShowCustomModal(false)}
          startDate={form.startDate}
          onSave={(customData) => {
            setForm((prev) => ({
              ...prev,
              repeatType: customData.frequency,
              customRecurrence: customData
            }));
            setShowCustomModal(false);
          }}
          initialValues={form.customRecurrence}
        />
      )}
    </>
  );
}

export function CustomRecurrenceModal({ open, onClose, startDate, onSave, initialValues }) {
  const weekdaysEn = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const weekdaysViMap = {
    Sun: "C",
    Mon: "H",
    Tue: "B",
    Wed: "T",
    Thu: "N",
    Fri: "S",
    Sat: "B"
  };
  const getInitialDay = () => {
    if (!startDate) return "Mon";
    const parts = startDate.split("-");
    const d = new Date(parts[0], parts[1] - 1, parts[2]);
    return weekdaysEn[d.getDay()];
  };

  const [interval, setIntervalVal] = useState(initialValues?.interval || 1);
  const [unit, setUnit] = useState(initialValues?.unit || "week");
  const [selectedDays, setSelectedDays] = useState(initialValues?.byDay || [getInitialDay()]);
  const [ends, setEnds] = useState(initialValues?.ends || "never");
  const [untilDate, setUntilDate] = useState(initialValues?.untilDate || formatDateInput(addDays(new Date(), 90)));
  const [count, setCount] = useState(initialValues?.count || 10);

  const toggleDay = (day) => {
    if (selectedDays.includes(day)) {
      if (selectedDays.length > 1) {
        setSelectedDays(selectedDays.filter((d) => d !== day));
      }
    } else {
      setSelectedDays([...selectedDays, day]);
    }
  };

  const handleDone = () => {
    const freqMap = {
      day: "custom_daily",
      week: "custom_weekly",
      month: "custom_monthly",
      year: "custom_yearly"
    };

    const savedData = {
      frequency: freqMap[unit],
      interval: Number(interval),
      unit,
      byDay: unit === "week" ? selectedDays : null,
      ends,
      untilDate: ends === "on" ? untilDate : null,
      count: ends === "after" ? Number(count) : null
    };

    onSave(savedData);
  };

  return (
    <Modal
      title="Tùy chỉnh lặp lại"
      open={open}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button variant="primary" onClick={handleDone}>
            Xong
          </Button>
        </>
      }
    >
      <div className="custom-rec-container">
        <div className="custom-rec-row">
          <span>Lặp lại mỗi</span>
          <input
            type="number"
            min="1"
            className="custom-rec-input-number"
            value={interval}
            onChange={(e) => setIntervalVal(Math.max(1, parseInt(e.target.value) || 1))}
          />
          <select
            className="custom-rec-select"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
          >
            <option value="day">ngày</option>
            <option value="week">tuần</option>
            <option value="month">tháng</option>
            <option value="year">năm</option>
          </select>
        </div>

        {unit === "week" && (
          <div>
            <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "8px" }}>Lặp lại vào</div>
            <div className="weekday-selector">
              {weekdaysEn.map((day) => {
                const isSelected = selectedDays.includes(day);
                const displayLetter = weekdaysViMap[day];
                return (
                  <button
                    key={day}
                    type="button"
                    className={`weekday-pill ${isSelected ? "selected" : ""}`}
                    onClick={() => toggleDay(day)}
                  >
                    {displayLetter}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div>
          <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "8px" }}>Kết thúc</div>
          <div className="ends-radio-group">
            <div className="ends-radio-option">
              <input
                type="radio"
                id="ends-never"
                name="ends"
                checked={ends === "never"}
                onChange={() => setEnds("never")}
              />
              <label htmlFor="ends-never">Không bao giờ</label>
            </div>

            <div className="ends-radio-option">
              <input
                type="radio"
                id="ends-on"
                name="ends"
                checked={ends === "on"}
                onChange={() => setEnds("on")}
              />
              <label htmlFor="ends-on" style={{ marginRight: "8px" }}>Vào ngày</label>
              <div className="ends-inline-inputs" style={{ opacity: ends === "on" ? 1 : 0.5, pointerEvents: ends === "on" ? "auto" : "none" }}>
                <input
                  type="date"
                  disabled={ends !== "on"}
                  value={untilDate}
                  onChange={(e) => setUntilDate(e.target.value)}
                  style={{
                    backgroundColor: ends === "on" ? "#fff" : "#f1f3f4",
                    color: ends === "on" ? "#3c4043" : "#9ca3af",
                    borderColor: ends === "on" ? "var(--surface-line)" : "transparent",
                    cursor: ends === "on" ? "text" : "not-allowed"
                  }}
                />
              </div>
            </div>

            <div className="ends-radio-option">
              <input
                type="radio"
                id="ends-after"
                name="ends"
                checked={ends === "after"}
                onChange={() => setEnds("after")}
              />
              <label htmlFor="ends-after" style={{ marginRight: "8px" }}>Sau</label>
              <div className="ends-inline-inputs" style={{ opacity: ends === "after" ? 1 : 0.5, pointerEvents: ends === "after" ? "auto" : "none" }}>
                <input
                  type="number"
                  min="1"
                  disabled={ends !== "after"}
                  value={count}
                  onChange={(e) => setCount(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{
                    backgroundColor: ends === "after" ? "#fff" : "#f1f3f4",
                    color: ends === "after" ? "#3c4043" : "#9ca3af",
                    borderColor: ends === "after" ? "var(--surface-line)" : "transparent",
                    cursor: ends === "after" ? "text" : "not-allowed"
                  }}
                />
                <span style={{ color: ends === "after" ? "#3c4043" : "#9ca3af" }}>lần lặp</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
