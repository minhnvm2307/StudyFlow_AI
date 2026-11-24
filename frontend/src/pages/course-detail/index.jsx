import { useEffect, useState, useMemo, useRef } from "react";
import { 
  ArrowLeft, BookOpen, Brain, Calendar, CheckCircle2, 
  HelpCircle, MessageSquare, Play, Sparkles, Trophy, RotateCcw, AlertTriangle,
  Pencil, Plus, Trash2, X, Check, GripVertical, FileText, ChevronDown, ChevronUp, ChevronLeft, ChevronRight
} from "lucide-react";
import { 
  AppShell, Badge, Button, Card, 
  PageContainer, ProgressBar, TopNav 
} from "../../components/common.jsx";
import { navigate } from "../../router.jsx";
import { coursesApi, quizApi, topicsApi, tasksApi } from "../../services/studyflowApi.js";
import { getCurrentUser } from "../../services/authSession.js";
import { QuizSetupModal } from "../study-workspace/QuizPanel.jsx";
import {
  buildCourseDetailQuizPayload,
  buildCourseDetailWorkspacePath,
} from "./quizActions.js";
import { buildTaskDisplayTitle, buildTasksByTopic, formatTaskSchedule } from "./taskGrouping.js";
import "./courseDetail.css";

export default function CourseDetailPage() {
  const courseId = window.location.pathname.split("/courses/detail/")[1]?.split("/")[0] || "";
  const courseDetailReturnPath = `${window.location.pathname}${window.location.search}`;
  const [course, setCourse] = useState(null);
  const [syllabus, setSyllabus] = useState(null);
  const [topics, setTopics] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editedLessons, setEditedLessons] = useState([]);
  const [isApproving, setIsApproving] = useState(false);
  const [generateQuizzes, setGenerateQuizzes] = useState(true);
  const [editingRow, setEditingRow] = useState(null);
  const [newSectionText, setNewSectionText] = useState("");
  const [expandedSubtopics, setExpandedSubtopics] = useState({});
  const [miniScheduleMonth, setMiniScheduleMonth] = useState("");
  const [quizSetupTopic, setQuizSetupTopic] = useState(null);
  const [quizBusy, setQuizBusy] = useState(false);
  const [quizActionError, setQuizActionError] = useState("");
  const newSectionInputRef = useRef(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState("");

  const handleRetryUploadedSyllabus = async () => {
    setActionLoading(true);
    setActionError("");
    try {
      await coursesApi.retryUploadedSyllabus(courseId);
      await fetchData();
    } catch (err) {
      setActionError(err.message || "Không thể thử lại syllabus đã tải lên.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateSyllabusFromSources = async () => {
    setActionLoading(true);
    setActionError("");
    try {
      await coursesApi.createSyllabusFromSources(courseId);
      await fetchData();
    } catch (err) {
      setActionError(err.message || "Không thể tạo syllabus từ tài liệu.");
    } finally {
      setActionLoading(false);
    }
  };

  useEffect(() => {
    if (syllabus?.syllabus?.status === "review_pending") {
      const initialLessons = syllabus?.syllabus?.parsedJson?.lessons || syllabus?.syllabus?.parsedJson?.normalizedLessons || [];
      setEditedLessons(JSON.parse(JSON.stringify(initialLessons)));
    }
  }, [syllabus]);

  const normalizeKey = (str) => {
    return String(str || "")
      .trim()
      .toLowerCase()
      .replace(/[.\s]+$/, "");
  };

  // Build a lookup: section text -> chapter-based number (e.g. "2.3")
  const sectionNumberMap = useMemo(() => {
    const chapters = syllabus?.syllabus?.parsedJson?.chapters || [];
    const map = new Map();
    for (const ch of chapters) {
      const chNum = ch.chapterNumber || ch.chapter_number || ch.number;
      if (!chNum) continue;
      (ch.sections || []).forEach((sec, i) => {
        const key = normalizeKey(sec);
        if (key && !map.has(key)) {
          map.set(key, `${chNum}.${i + 1}`);
        }
      });
    }
    return map;
  }, [syllabus]);

  const fetchData = async () => {
    try {
      console.log("[PROFILE] Starting fetchData...");
      const t_c_start = performance.now();
      const p_c = coursesApi.getCourse(courseId).then(res => {
        console.log(`[PROFILE] - GET /api/courses/${courseId} took ${(performance.now() - t_c_start).toFixed(2)}ms`);
        return res;
      });

      const t_s_start = performance.now();
      const p_s = coursesApi.getSyllabus(courseId).then(res => {
        console.log(`[PROFILE] - GET /api/courses/${courseId}/syllabus took ${(performance.now() - t_s_start).toFixed(2)}ms`);
        return res;
      });

      const t_ts_start = performance.now();
      const p_ts = topicsApi.getTopics(courseId).then(res => {
        console.log(`[PROFILE] - GET /api/courses/${courseId}/topics took ${(performance.now() - t_ts_start).toFixed(2)}ms`);
        return res;
      });

      const t_tsk_start = performance.now();
      const p_tsk = tasksApi.getTasks({ courseId }).then(res => {
        console.log(`[PROFILE] - GET /api/tasks?courseId=${courseId} took ${(performance.now() - t_tsk_start).toFixed(2)}ms`);
        return res;
      });

      const t_all_start = performance.now();
      const [c, s, ts, tsk] = await Promise.all([p_c, p_s, p_ts, p_tsk]);
      console.log(`[PROFILE] Parallel Promise.all(fetchData) took ${(performance.now() - t_all_start).toFixed(2)}ms`);

      setCourse(c);
      setSyllabus(s);
      setTopics(ts);
      setTasks(tsk);
      setError("");
    } catch (err) {
      setError(err.message || "Không thể tải thông tin môn học.");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleTaskStatus = async (e, task) => {
    e.stopPropagation();
    const newStatus = task.status === "done" ? "ready" : "done";
    try {
      await tasksApi.updateTask(task.id, { status: newStatus });
      await fetchData();
    } catch (err) {
      setError(err.message || "Không thể cập nhật trạng thái nhiệm vụ.");
    }
  };

  const handleUpdateLessonTitle = (index, title) => {
    setEditedLessons(prev => {
      const next = [...prev];
      next[index].title = title;
      return next;
    });
  };

  const handleUpdateWeekNumber = (index, week) => {
    setEditedLessons(prev => {
      const next = [...prev];
      next[index].week_number = Number(week) || null;
      return next;
    });
  };

  const handleAddSection = (lessonIndex, text) => {
    if (!text.trim()) return;
    setEditedLessons(prev => {
      const next = [...prev];
      next[lessonIndex].sections = [...(next[lessonIndex].sections || []), text.trim()];
      return next;
    });
  };

  const handleRemoveSection = (lessonIndex, sectionIndex) => {
    setEditedLessons(prev => {
      const next = [...prev];
      next[lessonIndex].sections = next[lessonIndex].sections.filter((_, idx) => idx !== sectionIndex);
      return next;
    });
  };

  const handleAddLesson = () => {
    setEditedLessons(prev => [
      ...prev,
      {
        week_number: prev.length + 1,
        lesson_number: prev.length + 1,
        title: `Bài mới ${prev.length + 1}`,
        sections: []
      }
    ]);
  };

  const handleRemoveLesson = (index) => {
    setEditedLessons(prev => prev.filter((_, idx) => idx !== index));
  };

  const handleApproveSyllabus = async () => {
    setIsApproving(true);
    console.log("[PROFILE] --- STARTING SYLLABUS APPROVAL FLOW ---");
    const t_total_start = performance.now();
    try {
      const planPayload = {
        availability: course.daysAvailable || ["Mon", "Wed", "Fri"],
        availabilityWindows: course.availabilityWindows || [],
        sessionMinutes: course.dailyGoalMinutes || 30,
        preferredStartTime: "09:00",
        startDate: new Date().toISOString().split("T")[0]
      };

      console.log("[PROFILE] Sending POST /approve-syllabus...");
      const t_post_start = performance.now();
      const resJson = await coursesApi.approveSyllabus(courseId, {
        lessons: editedLessons,
        planPayload,
        generateQuizzes
      });
      const t_post_end = performance.now();
      const post_duration = t_post_end - t_post_start;
      console.log(`[PROFILE] POST /approve-syllabus took ${post_duration.toFixed(2)}ms`);

      if (resJson && resJson.profile) {
        console.group("[PROFILE] Backend Server-Side Profiling Breakdown:");
        console.log(`- DB updates/inserts: ${(resJson.profile.db_took_seconds * 1000).toFixed(2)}ms`);
        console.log(`- map_syllabus: ${(resJson.profile.map_syllabus_took_seconds * 1000).toFixed(2)}ms`);
        console.log(`- generate_plan: ${(resJson.profile.generate_plan_took_seconds * 1000).toFixed(2)}ms`);
        console.log(`- update_onboarding_progress: ${(resJson.profile.update_onboarding_progress_took_seconds * 1000).toFixed(2)}ms`);
        console.log(`- Backend Total: ${(resJson.profile.total_took_seconds * 1000).toFixed(2)}ms`);
        console.groupEnd();
      }

      console.log("[PROFILE] Starting fetchData to refresh UI...");
      const t_fetch_start = performance.now();
      await fetchData();
      const t_fetch_end = performance.now();
      console.log(`[PROFILE] fetchData() took ${(t_fetch_end - t_fetch_start).toFixed(2)}ms`);
      
      console.log(`[PROFILE] --- TOTAL APPROVAL FLOW took ${(performance.now() - t_total_start).toFixed(2)}ms ---`);
    } catch (err) {
      setError(err.message || "Đã xảy ra lỗi khi phê duyệt.");
    } finally {
      setIsApproving(false);
    }
  };

  useEffect(() => {
    if (courseId) {
      fetchData();
    }
  }, [courseId]);

  // Poll if syllabus status is still processing or parsing
  useEffect(() => {
    let intervalId = null;
    const isProcessing = syllabus?.syllabus?.status === "processing" || syllabus?.syllabus?.status === "parsing";
    if (isProcessing) {
      intervalId = setInterval(() => {
        fetchData();
      }, 3000);
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [syllabus]);

  // Group topics by lesson
  const topicsByLesson = useMemo(() => {
    const map = {};
    topics.forEach((t) => {
      const key = t.lessonId || "unmapped";
      if (!map[key]) map[key] = [];
      map[key].push(t);
    });
    return map;
  }, [topics]);

  // Filter tasks by topic
  const tasksByTopic = useMemo(() => {
    return buildTasksByTopic(tasks, topics);
  }, [tasks, topics]);

  const scheduledTasks = useMemo(() => {
    return [...tasks]
      .filter((task) => task?.startAt)
      .sort((left, right) => new Date(left.startAt).getTime() - new Date(right.startAt).getTime());
  }, [tasks]);

  const taskSummary = useMemo(() => {
    const now = Date.now();
    const completed = tasks.filter((task) => task.status === "done").length;
    const missed = tasks.filter((task) => task.status === "missed").length;
    const upcoming = scheduledTasks.filter((task) => {
      const startAt = new Date(task.startAt).getTime();
      return startAt >= now && task.status !== "done" && task.status !== "missed";
    }).length;
    const overdue = scheduledTasks.filter((task) => {
      const startAt = new Date(task.startAt).getTime();
      return startAt < now && task.status !== "done" && task.status !== "missed";
    }).length;
    const activeDays = new Set(
      scheduledTasks.map((task) =>
        new Date(task.startAt).toLocaleDateString("en-CA", { timeZone: "Asia/Bangkok" })
      )
    ).size;

    return {
      totalScheduled: scheduledTasks.length,
      completed,
      missed,
      upcoming,
      overdue,
      activeDays,
    };
  }, [scheduledTasks, tasks]);

  const scheduledTasksByDate = useMemo(() => {
    return scheduledTasks.reduce((map, task) => {
      const startDate = new Date(task.startAt);
      if (Number.isNaN(startDate.getTime())) return map;
      const key = startDate.toLocaleDateString("en-CA", { timeZone: "Asia/Bangkok" });
      if (!map.has(key)) {
        map.set(key, []);
      }
      map.get(key).push(task);
      return map;
    }, new Map());
  }, [scheduledTasks]);

  const defaultMiniScheduleMonth = useMemo(() => {
    const now = Date.now();
    const anchorTask =
      scheduledTasks.find((task) => new Date(task.startAt).getTime() >= now) ||
      scheduledTasks[0] ||
      null;
    const anchorDate = anchorTask?.startAt ? new Date(anchorTask.startAt) : new Date();
    return `${anchorDate.getFullYear()}-${String(anchorDate.getMonth() + 1).padStart(2, "0")}`;
  }, [scheduledTasks]);

  useEffect(() => {
    if (!miniScheduleMonth) {
      setMiniScheduleMonth(defaultMiniScheduleMonth);
    }
  }, [defaultMiniScheduleMonth, miniScheduleMonth]);

  const miniScheduleCalendar = useMemo(() => {
    const monthKey = miniScheduleMonth || defaultMiniScheduleMonth;
    const [year, month] = monthKey.split("-").map(Number);
    const monthDate = new Date(year, (month || 1) - 1, 1);
    const firstDay = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
    const lastDay = new Date(monthDate.getFullYear(), monthDate.getMonth() + 1, 0);
    const startOffset = (firstDay.getDay() + 6) % 7;
    const totalDays = lastDay.getDate();
    const totalCells = Math.ceil((startOffset + totalDays) / 7) * 7;
    const todayKey = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Bangkok" });
    const examDateKey = course?.examDate
      ? new Date(course.examDate).toLocaleDateString("en-CA", { timeZone: "Asia/Bangkok" })
      : null;
    const days = [];

    for (let index = 0; index < totalCells; index += 1) {
      const dayNumber = index - startOffset + 1;
      const date = new Date(monthDate.getFullYear(), monthDate.getMonth(), dayNumber);
      const inMonth = dayNumber >= 1 && dayNumber <= totalDays;
      const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
      const dayTasks = inMonth ? scheduledTasksByDate.get(dateKey) || [] : [];
      const completed = dayTasks.filter((task) => task.status === "done").length;
      const missed = dayTasks.filter((task) => task.status === "missed").length;
      const isExamDay = inMonth && examDateKey && dateKey === examDateKey;

      days.push({
        dateKey,
        inMonth,
        dayNumber: date.getDate(),
        hasSessions: dayTasks.length > 0,
        isToday: inMonth && dateKey === todayKey,
        isExamDay,
        sessionCount: dayTasks.length,
        completed,
        missed,
      });
    }

    return {
      title: `tháng ${monthDate.getMonth() + 1} năm ${monthDate.getFullYear()}`,
      days,
      weekLabels: ["T2", "T3", "T4", "T5", "T6", "T7", "CN"],
    };
  }, [defaultMiniScheduleMonth, miniScheduleMonth, scheduledTasksByDate, course]);

  const changeMiniScheduleMonth = (direction) => {
    const monthKey = miniScheduleMonth || defaultMiniScheduleMonth;
    const [year, month] = monthKey.split("-").map(Number);
    const nextDate = new Date(year, (month || 1) - 1 + direction, 1);
    setMiniScheduleMonth(`${nextDate.getFullYear()}-${String(nextDate.getMonth() + 1).padStart(2, "0")}`);
  };

  const nextTask = useMemo(() => {
    return (
      scheduledTasks.find((task) => task.status !== "done" && task.status !== "missed") ||
      tasks.find((task) => task.status !== "done" && task.status !== "skipped") ||
      null
    );
  }, [scheduledTasks, tasks]);

  const toggleSubtopicSchedule = (topicId) => {
    setExpandedSubtopics((current) => ({
      ...current,
      [topicId]: !current[topicId],
    }));
  };

  const openTopicQuizSetup = (topic) => {
    setQuizActionError("");
    setQuizSetupTopic(topic);
  };

  const closeTopicQuizSetup = () => {
    if (quizBusy) return;
    setQuizSetupTopic(null);
  };

  const openTopicWorkspace = (topicId) => {
    navigate(
      buildCourseDetailWorkspacePath({
        courseId,
        topicId,
        returnTo: courseDetailReturnPath,
      })
    );
  };

  const handleGenerateTopicQuiz = async ({ count, difficulty, instructions }) => {
    if (!quizSetupTopic) return;

    setQuizBusy(true);
    setQuizActionError("");
    try {
      await quizApi.generateQuiz(
        buildCourseDetailQuizPayload({
          courseId,
          topicId: quizSetupTopic.id,
          count,
          difficulty,
          instructions,
        })
      );

      const topicId = quizSetupTopic.id;
      setQuizSetupTopic(null);
      openTopicWorkspace(topicId);
    } catch (err) {
      setQuizActionError(err.message || "Không thể tạo quiz cho chủ đề này.");
    } finally {
      setQuizBusy(false);
    }
  };

  if (loading) {
    return (
      <AppShell>
        <TopNav active="courses" />
        <PageContainer className="loading-container">
          <div className="loader-box">
            <div className="spinner"></div>
            <p>Đang tải lộ trình học tập...</p>
          </div>
        </PageContainer>
      </AppShell>
    );
  }

  if (error || !course) {
    return (
      <AppShell>
        <TopNav active="courses" />
        <PageContainer className="error-container">
          <Card className="error-card">
            <h3>Đã xảy ra lỗi</h3>
            <p>{error || "Không tìm thấy môn học."}</p>
            <Button onClick={() => navigate("/courses")}>Quay lại thư viện</Button>
          </Card>
        </PageContainer>
      </AppShell>
    );
  }

  if (syllabus?.syllabus?.status === "review_pending") {
    const isEditing = (idx) => editingRow === idx;
    const startEditing = (idx) => {
      setEditingRow(idx);
      setNewSectionText("");
    };
    const stopEditing = () => {
      setEditingRow(null);
      setNewSectionText("");
    };

    return (
      <AppShell>
        <TopNav active="courses" />
        <PageContainer className="course-detail-page">
          <header className="detail-header">
            <button className="back-btn" onClick={() => navigate("/courses")}>
              <ArrowLeft size={16} /> Quay lại thư viện
            </button>
            <div className="header-meta">
              <h1>Duyệt cấu trúc giáo trình: {course.name}</h1>
              <p className="syllabus-review-subtitle">
                <FileText size={16} style={{ flexShrink: 0 }} />
                AI đã trích xuất các buổi học & subtopics từ file syllabus của bạn. Nhấn biểu tượng <Pencil size={13} style={{ verticalAlign: "middle" }} /> để chỉnh sửa, sau đó ấn <strong>Xác nhận & Dựng lịch</strong>.
              </p>
            </div>
          </header>

          <div className="syllabus-doc">
            <div className="syllabus-doc-header">
              <div className="syllabus-doc-title-row">
                <h2 className="syllabus-doc-title">Kế hoạch giảng dạy</h2>
                <span className="syllabus-doc-course">{course.name}</span>
              </div>
              <div className="syllabus-doc-meta">
                <span>{editedLessons.length} buổi học</span>
                <span>•</span>
                <span>{editedLessons.reduce((sum, l) => sum + (l.sections?.length || 0), 0)} subtopics</span>
              </div>
            </div>

            <div className="syllabus-doc-body">
              {editedLessons.map((lesson, idx) => (
                <div 
                  className={`syllabus-lesson-row ${isEditing(idx) ? "editing" : ""}`}
                  key={idx}
                >
                  <div className="syllabus-week-badge">
                    <span className="week-num">Tuần {lesson.week_number || idx + 1}</span>
                  </div>

                  <div className="syllabus-lesson-content">
                    <div className="syllabus-lesson-title-row">
                      {isEditing(idx) ? (
                        <input
                          type="text"
                          className="syllabus-edit-input title-input"
                          value={lesson.title || ""}
                          onChange={(e) => handleUpdateLessonTitle(idx, e.target.value)}
                          placeholder="Tên buổi học..."
                          autoFocus
                        />
                      ) : (
                        <h3 className="syllabus-lesson-title">{lesson.title || `Bài ${idx + 1}`}</h3>
                      )}
                    </div>

                    <div className="syllabus-subtopics-row">
                      {(lesson.sections || []).map((section, sIdx) => {
                        const lookupKey = normalizeKey(section);
                        
                        // Resolve chapter number for fallback
                        let chNum = null;
                        const chapters = syllabus?.syllabus?.parsedJson?.chapters || [];
                        const lessonChNormalized = normalizeKey(lesson.chapter || "");
                        const matchingCh = chapters.find(ch => {
                          const chTitleNorm = normalizeKey(ch.title || "");
                          return chTitleNorm === lessonChNormalized || chTitleNorm.includes(lessonChNormalized) || lessonChNormalized.includes(chTitleNorm);
                        });
                        if (matchingCh) {
                          chNum = matchingCh.chapterNumber || matchingCh.chapter_number || matchingCh.number;
                        }
                        if (!chNum) {
                          const match = String(lesson.chapter || lesson.title || "").match(/(?:Chương|Chapter|Ch)\s*(\d+)/i);
                          chNum = match ? match[1] : null;
                        }
                        if (!chNum) {
                          chNum = lesson.lesson_number || lesson.week_number || idx + 1;
                        }

                        const label = sectionNumberMap.get(lookupKey) || `${chNum}.${sIdx + 1}`;
                        return (
                          <span key={sIdx} className="syllabus-subtopic-chip">
                            <span className="chip-number">{label}</span>
                            <span className="chip-text">{section}</span>
                            {isEditing(idx) && (
                              <button
                                className="chip-remove"
                                onClick={() => handleRemoveSection(idx, sIdx)}
                                title="Xóa subtopic"
                              >
                                <X size={12} />
                              </button>
                            )}
                          </span>
                        );
                      })}
                      {(lesson.sections || []).length === 0 && !isEditing(idx) && (
                        <span className="syllabus-no-subtopics">Chưa có subtopic</span>
                      )}
                    </div>

                    {isEditing(idx) && (
                      <div className="syllabus-add-section">
                        <input
                          ref={newSectionInputRef}
                          type="text"
                          className="syllabus-edit-input section-input"
                          placeholder="VD: 1.1 Khái niệm cơ bản..."
                          value={newSectionText}
                          onChange={(e) => setNewSectionText(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && newSectionText.trim()) {
                              handleAddSection(idx, newSectionText);
                              setNewSectionText("");
                            }
                          }}
                        />
                        <button
                          className="syllabus-add-btn"
                          onClick={() => {
                            if (newSectionText.trim()) {
                              handleAddSection(idx, newSectionText);
                              setNewSectionText("");
                              newSectionInputRef.current?.focus();
                            }
                          }}
                          title="Thêm subtopic"
                        >
                          <Plus size={14} />
                          <span>Thêm</span>
                        </button>
                      </div>
                    )}

                    {isEditing(idx) && (
                      <div className="syllabus-week-edit">
                        <label>Tuần:</label>
                        <input
                          type="number"
                          min="1"
                          className="syllabus-edit-input week-input"
                          value={lesson.week_number || ""}
                          onChange={(e) => handleUpdateWeekNumber(idx, e.target.value)}
                        />
                      </div>
                    )}
                  </div>

                  <div className="syllabus-lesson-actions">
                    {isEditing(idx) ? (
                      <>
                        <button
                          className="syllabus-action-icon done"
                          onClick={stopEditing}
                          title="Hoàn tất chỉnh sửa"
                        >
                          <Check size={16} />
                        </button>
                        <button
                          className="syllabus-action-icon delete"
                          onClick={() => {
                            handleRemoveLesson(idx);
                            stopEditing();
                          }}
                          title="Xóa buổi học"
                        >
                          <Trash2 size={16} />
                        </button>
                      </>
                    ) : (
                      <button
                        className="syllabus-action-icon edit"
                        onClick={() => startEditing(idx)}
                        title="Chỉnh sửa buổi học"
                      >
                        <Pencil size={16} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="syllabus-doc-footer">
              <button className="syllabus-add-lesson-btn" onClick={handleAddLesson}>
                <Plus size={16} />
                <span>Thêm buổi học mới</span>
              </button>
              <div className="syllabus-quiz-toggle">
                <label className="switch-label">
                  <input
                    type="checkbox"
                    checked={generateQuizzes}
                    onChange={(e) => setGenerateQuizzes(e.target.checked)}
                    className="switch-input"
                  />
                  <span className="switch-slider"></span>
                  <span className="switch-text">Tự động tạo câu hỏi ôn tập (quiz) cho các subtopics ngay bây giờ</span>
                </label>
              </div>
              <Button
                variant="primary"
                onClick={handleApproveSyllabus}
                disabled={isApproving || editedLessons.length === 0}
                className="syllabus-approve-btn"
              >
                {isApproving ? (
                  <>
                    <span className="spinner-sm"></span>
                    Đang dựng lịch học...
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={18} />
                    Xác nhận & Dựng lịch
                  </>
                )}
              </Button>
            </div>
          </div>
        </PageContainer>
      </AppShell>
    );
  }

  const isFailed = syllabus?.syllabus?.status === "failed";
  const isGenerating = !isFailed && (syllabus?.syllabus?.status === "processing" || syllabus?.syllabus?.status === "parsing" || !syllabus?.lessons?.length);

  return (
    <AppShell>
      <TopNav active="courses" />
      <PageContainer className="course-detail-page">
        <header className="detail-header">
          <button className="back-btn" onClick={() => navigate("/courses")}>
            <ArrowLeft size={16} /> Quay lại thư viện
          </button>
          <div className="header-meta">
            <h1>{course.name}</h1>
            <div className="badges-row">
              <Badge tone={course.priority === "high" ? "danger" : course.priority === "medium" ? "blue" : "neutral"} className="detail-meta-chip priority-chip">
                <span>Ưu tiên</span>
                <strong>{course.priority === "high" ? "Cao" : course.priority === "medium" ? "Trung bình" : "Thấp"}</strong>
              </Badge>
              <span className="meta-text">
                <span>Mục tiêu</span>
                <strong>{course.targetScore || 80}đ</strong>
              </span>
              <span className="meta-text">
                <span>Thi ngày</span>
                <strong>{course.examDate ? new Date(course.examDate).toLocaleDateString("vi-VN") : "Chưa đặt"}</strong>
              </span>
            </div>
          </div>
        </header>

        {isFailed ? (
          <Card className="failed-card">
            <div className="failed-visual">
              <AlertTriangle className="alert-icon" size={48} />
              <h2>Thiết lập môn học thất bại</h2>
              <p className="error-message">
                {actionError || 
                 syllabus?.syllabus?.parsedJson?.error || 
                 syllabus?.syllabus?.parsedJson?.progress?.detail || 
                 "Không thể trích xuất cấu trúc syllabus bài học từ tài liệu tải lên."}
              </p>
              <div className="action-buttons">
                <Button 
                  variant="primary" 
                  onClick={handleRetryUploadedSyllabus} 
                  disabled={actionLoading}
                >
                  {actionLoading ? "Đang xử lý..." : "Thử lại syllabus đã upload"}
                </Button>
                <Button 
                  variant="secondary" 
                  onClick={handleCreateSyllabusFromSources} 
                  disabled={actionLoading}
                >
                  {actionLoading ? "Đang xử lý..." : "Tạo syllabus từ tài liệu"}
                </Button>
                <Button 
                  variant="secondary" 
                  onClick={() => navigate("/courses")}
                  disabled={actionLoading}
                >
                  Quay lại thư viện
                </Button>
              </div>
            </div>
          </Card>
        ) : isGenerating ? (
          <Card className="generating-card">
            <div className="generating-visual">
              <Sparkles className="sparkle-icon animated" size={48} />
              <h2>Đang thiết lập môn học và xây dựng lộ trình...</h2>
              <p>Hệ thống AI đang đọc các tài liệu tải lên của bạn, trích xuất cấu trúc syllabus bài học chi tiết và tự động lập lịch ôn tập theo FSRS...</p>
              <div className="progress-bar-placeholder">
                <div className="progress-bar-fill"></div>
              </div>
            </div>
          </Card>
        ) : (
          <div className="detail-layout">
            <div className="detail-main">
              <section className="syllabus-roadmap">
                <h2 className="roadmap-title">Lộ trình học tập & Syllabus</h2>
                {quizActionError ? <p className="topic-action-error">{quizActionError}</p> : null}
                <div className="roadmap-timeline">
                  {syllabus?.lessons?.map((lesson, idx) => {
                    let lessonTopics = [...(topicsByLesson[lesson.id] || [])];
                    const hasSubtopics = lessonTopics.some((topic) => topic.isSubtopic);
                    if (hasSubtopics) {
                      lessonTopics = lessonTopics.filter((topic) => topic.isSubtopic);
                    }
                    lessonTopics.sort((left, right) => {
                      if (Boolean(left.isSubtopic) !== Boolean(right.isSubtopic)) {
                        return left.isSubtopic ? -1 : 1;
                      }
                      return (left.sectionNumber || left.orderIdx || 0) - (right.sectionNumber || right.orderIdx || 0);
                    });
                    return (
                      <div className="timeline-node" key={lesson.id}>
                        <div className="node-marker">
                          <span className="marker-dot">{idx + 1}</span>
                          {idx < syllabus.lessons.length - 1 && <span className="marker-line"></span>}
                        </div>
                        <div className="node-content">
                          <div className="lesson-header">
                            <h3>{lesson.title || `Bài ${lesson.lessonNumber || idx + 1}`}</h3>
                            {lesson.description && <p className="lesson-desc">{lesson.description}</p>}
                          </div>
                          <div className="topics-list">
                            {lessonTopics.map((topic) => {
                              const topicTasks = tasksByTopic[topic.id] || [];
                              const isWeak = topic.masteryPercent < 45;
                              const needsReview = topic.masteryPercent >= 45 && topic.masteryPercent < 70;
                              const isGood = topic.masteryPercent >= 70;
                              const isExpanded = Boolean(expandedSubtopics[topic.id]);
                              const sectionLabel = topic.sectionNumber 
                                ? `${topic.sectionNumber}` 
                                : (topic.isSubtopic ? "Subtopic" : "Chương");

                              return (
                                <Card className="topic-card subtopic-card" key={topic.id}>
                                  <div className="topic-card-header subtopic-card-header">
                                    <div className="topic-info">
                                      <span className="subtopic-index-chip">{sectionLabel}</span>
                                      <h4>{topic.title}</h4>
                                      {topic.description && <p className="topic-desc">{topic.description}</p>}
                                    </div>
                                    <div className="topic-stats">
                                      <div className="stat-pill" title="Độ thành thạo">
                                        <Trophy size={14} className={`trophy ${isGood ? "good" : isWeak ? "weak" : "needs-review"}`} />
                                        <span className="stat-value">{topic.masteryPercent}%</span>
                                      </div>
                                      <div className="stat-pill" title="Số lần ôn tập">
                                        <RotateCcw size={14} className="rotate-icon" />
                                        <span className="stat-value">{topic.reviewCount} lần</span>
                                      </div>
                                      {topic.hasQuiz ? (
                                        <Badge tone="green">Quiz sẵn sàng</Badge>
                                      ) : (
                                        <Badge tone="neutral">Chưa có Quiz</Badge>
                                      )}
                                      {topic.hasFlashcard ? (
                                        <Badge tone="green">Flashcard sẵn sàng</Badge>
                                      ) : (
                                        <Badge tone="neutral">Chưa có Flashcard</Badge>
                                      )}
                                      {topic.hasQuiz ? (
                                        <Button
                                          size="sm"
                                          variant="secondary"
                                          className="topic-quiz-btn"
                                          icon={Play}
                                          onClick={() => openTopicWorkspace(topic.id)}
                                        >
                                          Vào workspace
                                        </Button>
                                      ) : (
                                        <Button
                                          size="sm"
                                          variant="primary"
                                          className="topic-quiz-btn"
                                          icon={Sparkles}
                                          onClick={() => openTopicQuizSetup(topic)}
                                        >
                                          Tạo quiz
                                        </Button>
                                      )}
                                      <button
                                        type="button"
                                        className="schedule-toggle-btn"
                                        onClick={() => toggleSubtopicSchedule(topic.id)}
                                      >
                                        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                                        <span>{isExpanded ? "Thu gọn lịch" : `Xem lịch (${topicTasks.length})`}</span>
                                      </button>
                                    </div>
                                  </div>

                                  {isExpanded ? (
                                    <div className="topic-card-body">
                                    <div className="tasks-section">
                                      <h5>Nhiệm vụ được lên lịch:</h5>
                                      {topicTasks.length > 0 ? (
                                        <div className="tasks-grid">
                                          {topicTasks.map((t) => (
                                            <div 
                                              className={`task-row status-${t.status.toLowerCase()} clickable`}
                                              key={t.id}
                                              onClick={() => navigate(
                                                buildCourseDetailWorkspacePath({
                                                  courseId,
                                                  taskId: t.id,
                                                  returnTo: courseDetailReturnPath,
                                                })
                                              )}
                                            >
                                              <div className="task-left">
                                                <button 
                                                  className="task-status-toggle" 
                                                  onClick={(e) => handleToggleTaskStatus(e, t)} 
                                                  title={t.status === "done" ? "Đánh dấu chưa học" : "Đánh dấu đã học"}
                                                >
                                                  {t.status === "done" ? (
                                                    <CheckCircle2 size={16} className="done-icon" />
                                                  ) : t.status === "missed" ? (
                                                    <AlertTriangle size={16} className="missed-icon" />
                                                  ) : (
                                                    <Play size={16} className="play-icon" />
                                                  )}
                                                </button>
                                                <div className="task-copy">
                                                  <span className="task-title-text">{buildTaskDisplayTitle(t, topic.id)}</span>
                                                  {formatTaskSchedule(t) ? <span className="task-time-text">{formatTaskSchedule(t)}</span> : null}
                                                </div>
                                              </div>
                                              <Badge 
                                                tone={t.status === "done" ? "green" : t.status === "missed" ? "danger" : "blue"}
                                                className="task-badge-clickable"
                                                onClick={(e) => handleToggleTaskStatus(e, t)}
                                                title="Nhấp để đổi trạng thái"
                                              >
                                                {t.status === "done" ? "Hoàn thành" : t.status === "missed" ? "Trễ" : "Chưa học"}
                                              </Badge>
                                            </div>
                                          ))}
                                        </div>
                                      ) : (
                                        <div className="no-tasks">
                                          <span className="no-tasks-text">Không có nhiệm vụ nào được xếp lịch. Bạn có thể luyện tập tự do.</span>
                                          <Button 
                                            size="sm" 
                                            variant="secondary"
                                            onClick={() => navigate(
                                              buildCourseDetailWorkspacePath({
                                                courseId,
                                                topicId: topic.id,
                                                returnTo: courseDetailReturnPath,
                                              })
                                            )}
                                          >
                                            Luyện tập ngay
                                          </Button>
                                        </div>
                                      )}
                                      </div>
                                    </div>
                                  ) : null}
                                </Card>
                              );
                            })}
                            {lessonTopics.length === 0 && (
                              <p className="no-topics-hint">Chưa ánh xạ chủ đề học tập cho bài học này.</p>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            </div>

            <aside className="detail-sidebar">
              <Card className="summary-card">
                <div className="mini-schedule-card">
                  <div className="mini-schedule-header">
                    <div>
                      <h4>Lịch học</h4>
                      <p>Những ngày cần học môn này</p>
                    </div>
                    <div className="mini-schedule-nav">
                      <button type="button" className="mini-schedule-nav-btn" onClick={() => changeMiniScheduleMonth(-1)} aria-label="Tháng trước">
                        <ChevronLeft size={18} />
                      </button>
                      <button type="button" className="mini-schedule-nav-btn" onClick={() => changeMiniScheduleMonth(1)} aria-label="Tháng sau">
                        <ChevronRight size={18} />
                      </button>
                    </div>
                  </div>

                  {/* Calendar stats display */}
                  <div className="mini-calendar-stats" style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(3, 1fr)",
                    gap: "8px",
                    marginBottom: "14px",
                    padding: "8px",
                    background: "rgba(255, 255, 255, 0.6)",
                    borderRadius: "12px",
                    border: "1px solid rgba(148, 163, 184, 0.12)"
                  }}>
                    <div style={{ textAlign: "center" }}>
                      <span style={{ display: "block", fontSize: "10px", fontWeight: "700", textTransform: "uppercase", color: "var(--text-secondary)" }}>Tổng buổi</span>
                      <strong style={{ fontSize: "16px", color: "var(--text-primary)" }}>{taskSummary.totalScheduled}</strong>
                    </div>
                    <div style={{ textAlign: "center" }}>
                      <span style={{ display: "block", fontSize: "10px", fontWeight: "700", textTransform: "uppercase", color: "#dc2626" }}>Đã trễ</span>
                      <strong style={{ fontSize: "16px", color: "#dc2626" }}>{taskSummary.missed}</strong>
                    </div>
                    <div style={{ textAlign: "center" }}>
                      <span style={{ display: "block", fontSize: "10px", fontWeight: "700", textTransform: "uppercase", color: "#166534" }}>Đã xong</span>
                      <strong style={{ fontSize: "16px", color: "#166534" }}>{taskSummary.completed}</strong>
                    </div>
                  </div>

                  {taskSummary.totalScheduled > 0 ? (
                    <div className="mini-schedule-calendar">
                      <div className="mini-schedule-month-label">{miniScheduleCalendar.title}</div>
                      <div className="mini-schedule-weekdays">
                        {miniScheduleCalendar.weekLabels.map((label) => (
                          <span key={label}>{label}</span>
                        ))}
                      </div>
                      <div className="mini-schedule-grid">
                        {miniScheduleCalendar.days.map((day) => (
                          <button
                            type="button"
                            key={day.dateKey}
                            className={[
                              "mini-schedule-cell",
                              day.inMonth ? "" : "outside",
                              day.hasSessions ? "has-session" : "",
                              day.isToday ? "today" : "",
                              day.isExamDay ? "exam-day" : "",
                            ].filter(Boolean).join(" ")}
                            disabled={!day.inMonth}
                            title={
                              day.isExamDay
                                ? "NGÀY THI / HẠN CHÓT"
                                : day.hasSessions
                                ? `${day.sessionCount} study sessions`
                                : undefined
                            }
                          >
                            <span>{day.dayNumber}</span>
                            {day.hasSessions ? <i className="mini-schedule-dot" /> : null}
                            {day.isExamDay ? <i className="mini-schedule-exam-dot" /> : null}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="mini-schedule-empty">
                      Chưa có buổi học nào được lên lịch cho môn này.
                    </div>
                  )}
                </div>

                <div className="sidebar-actions">
                  <Button 
                    variant="primary" 
                    className="full-width-btn" 
                    icon={Play}
                    onClick={() => {
                      if (nextTask) {
                        navigate(
                          buildCourseDetailWorkspacePath({
                            courseId,
                            taskId: nextTask.id,
                            returnTo: courseDetailReturnPath,
                          })
                        );
                      } else {
                        navigate(
                          buildCourseDetailWorkspacePath({
                            courseId,
                            returnTo: courseDetailReturnPath,
                          })
                        );
                      }
                    }}
                  >
                    Bắt đầu học tiếp
                  </Button>
                  <Button 
                    variant="secondary" 
                    className="full-width-btn" 
                    icon={MessageSquare}
                    onClick={() => navigate(
                      buildCourseDetailWorkspacePath({
                        courseId,
                        returnTo: courseDetailReturnPath,
                      })
                    )}
                  >
                    Hỏi đáp AI Workspace
                  </Button>
                </div>
              </Card>
            </aside>
          </div>
        )}
        <QuizSetupModal
          open={Boolean(quizSetupTopic)}
          onClose={closeTopicQuizSetup}
          onSubmit={handleGenerateTopicQuiz}
          busy={quizBusy}
          selectedCount={0}
        />
      </PageContainer>
    </AppShell>
  );
}
