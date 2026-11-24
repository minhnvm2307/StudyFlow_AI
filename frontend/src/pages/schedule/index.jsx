import { useEffect, useMemo, useState, useRef } from "react";
import { CalendarPlus, ChevronLeft, ChevronRight, Plus, AlertTriangle, RotateCcw } from "lucide-react";
import { Button, Card, IconButton, SearchInput, TopNav } from "../../components/common.jsx";
import { busyEventsApi, coursesApi, tasksApi, quizApi, topicsApi } from "../../services/studyflowApi.js";
import {
  addDays,
  buildDays,
  CreateBusyEventModal,
  CreateTaskModal,
  DaySchedule,
  HourAxis,
  EventPopover,
  LeftPanel,
  RescheduleModal,
  startOfWeek
} from "./components.jsx";

export default function SchedulePage() {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [courses, setCourses] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [busyEvents, setBusyEvents] = useState([]);
  const [syllabi, setSyllabi] = useState([]);
  const [quizzes, setQuizzes] = useState([]);
  const [topics, setTopics] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [busyModalOpen, setBusyModalOpen] = useState(false);
  const [rescheduleModalOpen, setRescheduleModalOpen] = useState(false);
  const [editingBusyEvent, setEditingBusyEvent] = useState(null);
  const [rescheduling, setRescheduling] = useState(false);
  const [error, setError] = useState("");

  const calendarGridRef = useRef(null);

  useEffect(() => {
    if (calendarGridRef.current) {
      calendarGridRef.current.scrollTop = 420;
    }
  }, []);

  // Filters
  const [selectedCourseIds, setSelectedCourseIds] = useState(() => new Set());
  const [showTasks, setShowTasks] = useState(true);
  const [showClass, setShowClass] = useState(true);
  const [showExam, setShowExam] = useState(true);
  const [showBusy, setShowBusy] = useState(true);

  const days = useMemo(() => buildDays(weekStart), [weekStart]);
  const courseById = useMemo(() => new Map(courses.map((course) => [course.id, course])), [courses]);
  const infeasibleCourses = useMemo(() => courses.filter((course) => course.coverageWarning === "INFEASIBLE"), [courses]);
  const showInfeasibleEmpty = infeasibleCourses.length > 0 && tasks.length === 0;
  const academicEvents = useMemo(() => buildAcademicEvents(courses, syllabi, days), [courses, syllabi, days]);
  
  const scheduleItems = useMemo(() => {
    const taskItems = tasks.map((task) => ({ ...task, itemKind: "task" }));
    const busyItems = busyEvents.map((event) => ({ ...event, itemKind: "busy" }));
    
    const filteredItems = [...taskItems, ...busyItems, ...academicEvents].filter((item) => {
      // 1. Filter by item kind / type
      if (item.itemKind === "busy") {
        if (!showBusy) return false;
      } else if (item.itemKind === "exam") {
        if (!showExam) return false;
      } else if (item.itemKind === "class") {
        if (!showClass) return false;
      } else if (item.itemKind === "task") {
        if (!showTasks) return false;
      }

      // 2. Filter by course
      if (item.courseId) {
        return selectedCourseIds.has(item.courseId);
      }
      return true;
    });

    return splitItemsByDay(filteredItems, days)
      .sort((a, b) => new Date(a.startAt) - new Date(b.startAt));
  }, [tasks, busyEvents, academicEvents, days, selectedCourseIds, showTasks, showClass, showExam, showBusy]);

  const hasOverlap = useMemo(() => {
    return tasks.some(task => {
      if (task.status === "done") return false;
      if (!task.startAt || !task.endAt) return false;
      const tStart = new Date(task.startAt).getTime();
      const tEnd = new Date(task.endAt).getTime();

      return busyEvents.some(event => {
        if (!event.startAt || !event.endAt) return false;
        const eStart = new Date(event.startAt).getTime();
        const eEnd = new Date(event.endAt).getTime();

        return tStart < eEnd && tEnd > eStart;
      });
    });
  }, [tasks, busyEvents]);

  const loadStaticData = () => {
    coursesApi.getCourses()
      .then(async (courseItems) => {
        setCourses(courseItems);
        setSelectedCourseIds((prev) => {
          if (prev.size === 0) {
            return new Set(courseItems.map((c) => c.id));
          }
          return prev;
        });

        const [syllabusItems, quizListGroup, topicListGroup] = await Promise.all([
          Promise.all(courseItems.map((course) => coursesApi.getSyllabus(course.id).catch(() => null))),
          Promise.all(courseItems.map((course) => quizApi.getQuizzes(course.id).catch(() => []))),
          Promise.all(courseItems.map((course) => topicsApi.getTopics(course.id).catch(() => [])))
        ]);

        setSyllabi(syllabusItems.filter(Boolean));
        setQuizzes(quizListGroup.flat());
        setTopics(topicListGroup.flat());
      })
      .catch((err) => setError(err.message || "Không thể tải thông tin môn học."));
  };

  const loadWeeklyData = () => {
    const start = weekStart.toISOString();
    const end = addDays(weekStart, 7).toISOString();
    Promise.all([
      tasksApi.getTasks({ start, end }),
      busyEventsApi.getBusyEvents({ start, end })
    ])
      .then(([taskItems, busyItems]) => {
        setTasks(taskItems);
        setBusyEvents(busyItems);
        setError("");
      })
      .catch((err) => setError(err.message || "Không thể tải lịch học tuần này."));
  };

  const loadData = () => {
    loadWeeklyData();
  };

  useEffect(() => {
    loadStaticData();
  }, []);

  useEffect(() => {
    loadWeeklyData();
  }, [weekStart]);

  const handleCreateTask = async (payload) => {
    await tasksApi.createTask(payload);
    setTaskModalOpen(false);
    loadData();
  };

  const handleSaveBusyEvent = async (payload) => {
    if (editingBusyEvent) {
      await busyEventsApi.updateBusyEvent(editingBusyEvent.id, payload);
    } else {
      await busyEventsApi.createBusyEvent(payload);
    }
    setBusyModalOpen(false);
    setEditingBusyEvent(null);
    loadData();
  };

  const handleReschedule = async (payload) => {
    setRescheduling(true);
    try {
      const res = await tasksApi.reschedule({ strategy: "keep_workload", ...payload });
      setRescheduleModalOpen(false);
      loadData();
      if (res && res.notifications && res.notifications.length > 0) {
        alert("Thông báo dời lịch học:\n\n" + res.notifications.join("\n"));
      }
    } finally {
      setRescheduling(false);
    }
  };

  const openBusyModal = (event = null) => {
    setEditingBusyEvent(event);
    setBusyModalOpen(true);
  };

  const handleDeleteBusyEvent = async (eventId, deleteSeries = false) => {
    await busyEventsApi.deleteBusyEvent(eventId, deleteSeries);
    setSelectedEvent(null);
    loadData();
  };

  return (
    <div className="calendar-shell">
      <TopNav active="schedule" />
      <div className="calendar-toolbar">
        <div className="calendar-toolbar-left">
          <Button variant="secondary" onClick={() => setWeekStart(startOfWeek(new Date()))}>Hôm nay</Button>
          <IconButton icon={ChevronLeft} label="Tuần trước" onClick={() => setWeekStart(addDays(weekStart, -7))} />
          <IconButton icon={ChevronRight} label="Tuần sau" onClick={() => setWeekStart(addDays(weekStart, 7))} />
          <h1>{days[0].dateLabel} - {days[6].dateLabel}</h1>
        </div>
        <div className="calendar-toolbar-right">
          <SearchInput placeholder="Tìm lịch..." />
          <Button variant="primary">Tuần</Button>
          <Button variant="secondary">Lịch biểu</Button>
          <Button variant="secondary" icon={Plus} onClick={() => setTaskModalOpen(true)}>Tạo nhiệm vụ</Button>
          <Button variant="primary" icon={CalendarPlus} onClick={() => openBusyModal()}>Tạo sự kiện bận</Button>
        </div>
      </div>

      <div className="calendar-page">
        <LeftPanel
          courses={courses}
          missedCount={tasks.filter((task) => task.status === "missed").length}
          busyCount={busyEvents.length}
          examCount={academicEvents.filter((item) => item.itemKind === "exam").length}
          classCount={academicEvents.filter((item) => item.itemKind === "class").length}
          onCreateTask={() => setTaskModalOpen(true)}
          onCreateBusyEvent={() => openBusyModal()}
          onReschedule={() => setRescheduleModalOpen(true)}
          tasks={tasks}
          academicEvents={academicEvents}
          selectedCourseIds={selectedCourseIds}
          setSelectedCourseIds={setSelectedCourseIds}
          showTasks={showTasks}
          setShowTasks={setShowTasks}
          showClass={showClass}
          setShowClass={setShowClass}
          showExam={showExam}
          setShowExam={setShowExam}
          showBusy={showBusy}
          setShowBusy={setShowBusy}
          weekStart={weekStart}
          onWeekStartChange={setWeekStart}
        />
        <div className="calendar-grid-wrapper" ref={calendarGridRef}>
          {error ? <Card className="stack-card">{error}</Card> : null}
          {showInfeasibleEmpty ? (
            <Card className="stack-card">
              <strong>Cannot generate study tasks</strong>
              <p>{infeasibleCourses.map((course) => course.name).join(", ")} has no schedulable study time for this plan. Adjust availability or busy events, then rebuild the schedule.</p>
            </Card>
          ) : null}
          {hasOverlap ? (
            <Card className="stack-card" style={{
              background: "#fff8db",
              border: "1px solid #f3d574",
              borderRadius: "8px",
              padding: "16px",
              marginBottom: "16px",
              color: "#6b5200",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center"
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <AlertTriangle size={24} style={{ color: "#d97706", flexShrink: 0 }} />
                <div>
                  <strong style={{ color: "#b45309", fontSize: "15px", display: "block", marginBottom: "4px" }}>
                    Lịch học đang bị trùng!
                  </strong>
                  <span style={{ fontSize: "13px" }}>
                    Một số sự kiện bận của bạn đang đè lên lịch học do hệ thống đề xuất trong tuần này. Hãy ấn <strong>Lập lại lịch</strong> để hệ thống sắp xếp lại thời gian tối ưu cho bạn.
                  </span>
                </div>
              </div>
              <div style={{ flexShrink: 0, marginLeft: "16px" }}>
                <Button
                  variant="primary"
                  icon={RotateCcw}
                  onClick={() => setRescheduleModalOpen(true)}
                >
                  Lập lại lịch
                </Button>
              </div>
            </Card>
          ) : null}
          <div className="week-stack" style={{ gridTemplateColumns: "60px repeat(7, minmax(136px, 1fr))" }}>
            <HourAxis />
            {days.map((day) => (
              <DaySchedule
                key={day.key}
                day={day}
                items={scheduleItems}
                courseById={courseById}
                onSelect={setSelectedEvent}
              />
            ))}
          </div>
        </div>
      </div>

      <EventPopover
        event={selectedEvent}
        courseById={courseById}
        quizzes={quizzes}
        topics={topics}
        syllabi={syllabi}
        onClose={() => setSelectedEvent(null)}
        onEditBusy={openBusyModal}
        onDeleteBusy={handleDeleteBusyEvent}
      />
      <CreateTaskModal open={taskModalOpen} courses={courses} onClose={() => setTaskModalOpen(false)} onCreate={handleCreateTask} />
      <CreateBusyEventModal
        open={busyModalOpen}
        event={editingBusyEvent}
        onClose={() => {
          setBusyModalOpen(false);
          setEditingBusyEvent(null);
        }}
        onCreate={handleSaveBusyEvent}
      />
      <RescheduleModal
        open={rescheduleModalOpen}
        courses={courses}
        missedCount={tasks.filter((task) => task.status === "missed").length}
        busy={rescheduling}
        onClose={() => setRescheduleModalOpen(false)}
        onSubmit={handleReschedule}
      />
    </div>
  );
}

const weekdayKeys = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function buildAcademicEvents(courses, syllabi, days) {
  const syllabiByCourse = new Map(syllabi.map((item) => [item.courseId, item]));
  const dayKeys = new Set(days.map((day) => day.key));
  return courses.flatMap((course) => [
    ...buildExamEvents(course, dayKeys),
    ...buildClassEvents(course, syllabiByCourse.get(course.id), days)
  ]);
}

function buildExamEvents(course, dayKeys) {
  const examDate = String(course.examDate || "").slice(0, 10);
  if (!examDate || !dayKeys.has(examDate)) return [];
  return [{
    id: `exam-${course.id}-${examDate}`,
    itemKind: "exam",
    courseId: course.id,
    title: `Thi: ${course.name}`,
    type: "exam",
    startAt: dateTimeIso(examDate, "08:00"),
    endAt: dateTimeIso(examDate, "09:00"),
    status: "scheduled",
    reason: "Lịch thi của môn học."
  }];
}

function buildClassEvents(course, syllabusData, days) {
  if (!syllabusData?.lessons?.length) return [];
  const calendar = syllabusData.syllabus?.parsedJson?.calendar || {};
  const meetings = Array.isArray(calendar.classMeetings) ? calendar.classMeetings : [];

  if (!meetings.length) {
    return syllabusData.lessons
      .filter((lesson) => lesson.startsOn && days.some((day) => day.key === String(lesson.startsOn).slice(0, 10)))
      .map((lesson) => classEventFromLesson(course, lesson, String(lesson.startsOn).slice(0, 10), "08:00", "09:00"));
  }

  return days.flatMap((day) => meetings
    .filter((meeting) => meeting.day === weekdayKeys[day.date.getDay()])
    .filter(() => isWithinRange(day.key, calendar.semesterStartDate, calendar.semesterEndDate))
    .map((meeting) => classEventFromLesson(course, lessonForDate(syllabusData.lessons, day.key), day.key, meeting.start, meeting.end))
  );
}

function classEventFromLesson(course, lesson, dateKey, start, end) {
  const rawTitle = lesson?.title || "Buổi học trên trường";
  // assignedReadings[0] contains the chapter string extracted from syllabus by LLM (e.g. "Chương 3")
  const chapterHint = String(lesson?.assignedReadings?.[0] || "").trim();
  const chapterPrefix = chapterHint && !rawTitle.startsWith("Chương") && !rawTitle.startsWith("chương")
    ? `${chapterHint} - `
    : "";
  const lessonTitle = `${chapterPrefix}${rawTitle}`;
  const display = classLessonDisplay(lesson, lessonTitle);
  return {
    id: `class-${course.id}-${dateKey}-${start}`,
    itemKind: "class",
    courseId: course.id,
    lessonId: lesson?.id,
    lessonTitle: display.sectionTitle || display.title,
    classChapterTitle: display.chapterTitle,
    classSectionTitle: display.sectionTitle,
    title: display.title,
    type: "class",
    startAt: dateTimeIso(dateKey, start || "08:00"),
    endAt: dateTimeIso(dateKey, end || "09:00"),
    status: lesson?.status || "scheduled",
    reason: "System-suggested study block derived from the on-campus lesson."
  };
}

function classLessonDisplay(lesson, fallbackTitle) {
  const rawTitle = String(lesson?.title || "").trim();
  const description = String(lesson?.description || "").replace(/\r/g, "");
  const lines = description.split("\n").map((line) => line.trim()).filter(Boolean);
  const chapterLine = lines.find((line) => startsWithChapterTitle(line)) || "";
  const sectionLines = lines.filter((line) => line !== chapterLine && startsWithSectionNumber(line));
  const chapterHint = String(lesson?.assignedReadings?.[0] || "").trim();
  const chapterTitle = chapterLine || (startsWithChapterTitle(rawTitle) ? rawTitle : chapterHint);
  const sectionTitle = sectionLines.join(" ") || (!startsWithChapterTitle(rawTitle) ? rawTitle : "");
  const title = chapterTitle || fallbackTitle || rawTitle;
  return { title, chapterTitle: chapterTitle || title, sectionTitle };
}

function startsWithChapterTitle(value) {
  return /^\s*(?:ch\u01b0\u01a1ng|chuong|chapter)\s+[0-9ivxlcdm]+\b/i.test(String(value || ""));
}

function startsWithSectionNumber(value) {
  return /^\s*\d+(?:\.\d+)*[.)]?\s+\S/.test(String(value || ""));
}


function lessonForDate(lessons, dateKey) {
  return lessons.find((lesson) => isWithinRange(dateKey, lesson.startsOn, lesson.endsOn))
    || lessons.find((lesson) => String(lesson.startsOn || "").slice(0, 10) === dateKey)
    || null;
}

function isWithinRange(dateKey, start, end) {
  const startKey = String(start || "").slice(0, 10);
  const endKey = String(end || "").slice(0, 10);
  return (!startKey || dateKey >= startKey) && (!endKey || dateKey <= endKey);
}

function dateTimeIso(dateKey, timeValue) {
  return new Date(`${dateKey}T${timeValue || "08:00"}:00`).toISOString();
}

function splitItemsByDay(items, days) {
  return items.flatMap((item) => splitItemByDay(item, days));
}

function splitItemByDay(item, days) {
  const originalStart = new Date(item.startAt);
  const originalEnd = new Date(item.endAt);
  if (!Number.isFinite(originalStart.getTime()) || !Number.isFinite(originalEnd.getTime()) || originalEnd <= originalStart) {
    return [item];
  }

  const segments = [];
  days.forEach((day) => {
    const dayStart = new Date(day.date);
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = addDays(dayStart, 1);
    const segmentStart = new Date(Math.max(originalStart.getTime(), dayStart.getTime()));
    const segmentEnd = new Date(Math.min(originalEnd.getTime(), dayEnd.getTime()));
    if (segmentStart < segmentEnd) {
      segments.push({
        ...item,
        startAt: segmentStart.toISOString(),
        endAt: segmentEnd.toISOString(),
        originalStartAt: item.originalStartAt || item.startAt,
        originalEndAt: item.originalEndAt || item.endAt,
        displayStartTime: segmentStart.getTime() === dayStart.getTime() && originalStart < dayStart ? "00:00" : null,
        displayEndTime: segmentEnd.getTime() === dayEnd.getTime() ? "24:00" : null,
        segmentDateKey: day.key,
        isSplitSegment: originalStart < dayStart || originalEnd > dayEnd
      });
    }
  });
  return segments;
}
