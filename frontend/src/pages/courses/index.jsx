import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, BookOpenText, Clock3, Plus, SlidersHorizontal, Sparkles, Trash2 } from "lucide-react";
import {
  Badge,
  Button,
  AppShell,
  Card,
  PageContainer,
  ProgressBar,
  SearchInput,
  SegmentedControl,
  TopNav
} from "../../components/common.jsx";
import { navigate } from "../../router.jsx";
import { coursesApi } from "../../services/studyflowApi.js";
import { CourseConfigModal } from "./CourseConfigModal.jsx";

const filters = ["Môn đã học gần đây", "Tất cả"];

const modeLabels = {
  continuous: "Học kỳ liên tục",
  exam_sprint: "Ôn thi tăng tốc"
};

const priorityLabels = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao"
};

const statusLabels = {
  on_track: "Đúng tiến độ",
  needs_attention: "Cần chú ý",
  behind: "Chậm",
  not_enough_data: "Chưa đủ dữ liệu",
  scheduling: "Đang lập lịch"
};

function mapApiCourse(course) {
  const tone = course.priority === "high" ? "green" : course.priority === "medium" ? "blue" : "gray";
  const syllabusStatus = course.syllabusStatus || "";
  const sourceCount = course.sourceCount || 0;
  const taskCount = course.taskCount || 0;
  const isScheduling = ["processing", "parsing", "uploaded"].includes(syllabusStatus) || (sourceCount > 0 && taskCount === 0);
  const displayStatus = isScheduling ? "scheduling" : course.status;
  return {
    id: course.id,
    name: course.name,
    shortName: course.name,
    mode: modeLabels[course.mode] || course.mode,
    examLabel: course.examDate ? new Date(course.examDate).toLocaleDateString("vi-VN") : "Chưa đặt ngày thi",
    examDate: course.examDate || "",
    sourceCount,
    taskCount,
    mastery: course.masteryPercent || 0,
    confidence: course.confidencePercent || 0,
    masteryPercent: course.masteryPercent || 0,
    confidencePercent: course.confidencePercent || 0,
    status: statusLabels[displayStatus] || displayStatus,
    priority: priorityLabels[course.priority] || course.priority,
    updatedAt: course.updatedAt ? new Date(course.updatedAt).toLocaleDateString("vi-VN") : "Vừa tạo",
    syllabusStatus,
    isScheduling,
    tone,
    icon: course.name?.trim()?.charAt(0)?.toUpperCase() || "S",
    featured: isScheduling || course.featured || course.priority === "high" || course.status === "needs_attention"
  };
}

function CourseGlyph({ course }) {
  return (
    <div className={`course-glyph tone-${course.tone}`}>
      <span>{course.icon}</span>
    </div>
  );
}

function openCourse(course) {
  navigate(`/courses/detail/${course.id}`);
}

function handleCourseKeyDown(event, course) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    openCourse(course);
  }
}

function FeaturedCourseCard({ course, deleting, onDelete, onConfig }) {
  return (
    <Card
      className={`featured-course tone-${course.tone} clickable-course`}
      as="article"
      role="button"
      tabIndex={0}
      onClick={() => openCourse(course)}
      onKeyDown={(event) => handleCourseKeyDown(event, course)}
    >
      <div className="featured-course-glow" />
      <div className="featured-art">
        <CourseGlyph course={course} />
      </div>
      <div className="featured-body">
        <div className="course-card-head">
          <h3>{course.name}</h3>
          <div className="course-card-actions">
            <button type="button" aria-label="Mở môn" onClick={(event) => { event.stopPropagation(); openCourse(course); }}>
              <ArrowUpRight size={18} />
            </button>
            <button type="button" className="course-config-button" aria-label={`Cấu hình môn ${course.name}`} onClick={(event) => { event.stopPropagation(); onConfig(course); }}>
              <SlidersHorizontal size={15} />
            </button>
            <button
              type="button"
              className="course-delete-button"
              aria-label={`Xóa môn ${course.name}`}
              disabled={deleting}
              onClick={(event) => { event.stopPropagation(); event.preventDefault(); onDelete(course); }}
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>
        <div className="course-badges">
          {course.isScheduling ? <Badge tone="amber" className="scheduling-badge">Đang lập lịch</Badge> : null}
          <Badge tone={course.mode.includes("Ôn") ? "green" : "neutral"}>{course.mode}</Badge>
          <span>{course.examLabel} · {course.sourceCount} nguồn</span>
        </div>
        <div className="course-progress-line">
          <span>Thành thạo</span>
          <strong>{course.mastery}% · {course.confidence}%</strong>
        </div>
        <ProgressBar value={course.mastery} tone={course.tone} />
      </div>
    </Card>
  );
}

function RecentCourseCard({ course, deleting, onDelete, onConfig }) {
  return (
    <Card
      className="recent-course clickable-course"
      as="article"
      role="button"
      tabIndex={0}
      onClick={() => openCourse(course)}
      onKeyDown={(event) => handleCourseKeyDown(event, course)}
    >
      <div className="recent-course-shine" />
      <div className="recent-top">
        <CourseGlyph course={course} />
        <div style={{ display: "flex", gap: "6px" }}>
          <button type="button" className="course-config-button" aria-label={`Cấu hình môn ${course.name}`} onClick={(event) => { event.stopPropagation(); onConfig(course); }}><SlidersHorizontal size={15} /></button>
          <button
            type="button"
            className="course-delete-button"
            aria-label={`Xóa môn ${course.name}`}
            disabled={deleting}
            onClick={(event) => { event.stopPropagation(); event.preventDefault(); onDelete(course); }}
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      <h3>{course.name}</h3>
      <p>{course.updatedAt} · {course.sourceCount} nguồn</p>
      {course.isScheduling ? (
        <div className="course-card-status">
          <Badge tone="amber" className="scheduling-badge">Đang lập lịch</Badge>
        </div>
      ) : null}
      <div className="course-progress-line">
        <span>{course.status}</span>
        <strong>{course.mastery}% · {course.confidence}%</strong>
      </div>
      <ProgressBar value={course.mastery} tone={course.tone} />
    </Card>
  );
}

export default function CoursesPage() {
  const [apiCourses, setApiCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState("");
  const [configCourseId, setConfigCourseId] = useState(null);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState(filters[0]);

  const loadCourses = (silent = false) => {
    if (!silent) setLoading(true);
    coursesApi.getCourses()
      .then((items) => {
        setApiCourses(items.map(mapApiCourse));
        setError("");
      })
      .catch((err) => {
        setError(err.message || "Không thể tải danh sách môn học.");
      })
      .finally(() => {
        if (!silent) setLoading(false);
      });
  };

  useEffect(() => {
    loadCourses();
  }, []);

  useEffect(() => {
    if (!apiCourses.some((course) => course.isScheduling)) return undefined;
    const timer = window.setInterval(() => loadCourses(true), 5000);
    return () => window.clearInterval(timer);
  }, [apiCourses]);

  const visibleCourses = useMemo(() => {
    const query = searchQuery.toLowerCase().trim();
    return apiCourses.filter((course) => {
      const matchesSearch = !query || course.name.toLowerCase().includes(query);
      if (!matchesSearch) return false;
      if (activeFilter === "Môn đã học gần đây") {
        return course.masteryPercent > 0 || course.taskCount > 0 || course.sourceCount > 0;
      }
      return true;
    });
  }, [activeFilter, apiCourses, searchQuery]);

  const visibleRecentCourses = visibleCourses;
  const featuredCourses = useMemo(() => {
    const selected = visibleCourses.filter((course) => course.featured || course.priority === "Cao" || course.status === "Cần chú ý");
    return selected.length ? selected : visibleCourses;
  }, [visibleCourses]);
  const schedulingCount = useMemo(() => apiCourses.filter((course) => course.isScheduling).length, [apiCourses]);
  const highPriorityCount = useMemo(() => apiCourses.filter((course) => course.priority === "Cao").length, [apiCourses]);
  const averageMastery = useMemo(() => (
    apiCourses.length ? Math.round(apiCourses.reduce((sum, course) => sum + (course.mastery || 0), 0) / apiCourses.length) : 0
  ), [apiCourses]);
  const totalSources = useMemo(() => apiCourses.reduce((sum, course) => sum + (course.sourceCount || 0), 0), [apiCourses]);

  const handleDeleteCourse = async (course) => {
    const confirmed = window.confirm(`Xóa môn "${course.name}"? Lịch học, tài liệu, topic, quiz, flashcard và chat của môn này sẽ bị xóa.`);
    if (!confirmed) return;
    setDeletingId(course.id);
    try {
      await coursesApi.deleteCourse(course.id);
      setApiCourses((current) => current.filter((item) => item.id !== course.id));
      setError("");
    } catch (err) {
      setError(err.message || "Không thể xóa môn học.");
    } finally {
      setDeletingId("");
    }
  };

  return (
    <AppShell>
      <TopNav active="courses" />
      <PageContainer className="courses-page">

        <div className="library-toolbar">
          <div className="library-actions" style={{ width: "100%", justifyContent: "space-between", gap: "16px" }}>
            <div className="library-toolbar-main">
              <SearchInput
                placeholder="Tìm môn học..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <SegmentedControl options={filters} active={activeFilter} onChange={setActiveFilter} className="courses-filter-control" />
            </div>
            <Button variant="primary" icon={Plus} onClick={() => navigate("/courses/new")}>Tạo mới</Button>
          </div>
        </div>

        <section className="course-section course-section-featured">
          <div className="course-section-head">
            <div>
              <h2>Môn học nổi bật</h2>
              <p className="course-section-copy">Những môn đang cần chú ý, ưu tiên cao hoặc đang được hệ thống lập lịch.</p>
            </div>
            <Button variant="ghost" icon={ArrowUpRight}>Xem tất cả</Button>
          </div>
          <div className="featured-grid">
            {loading ? <Card className="recent-course"><h3>Đang tải môn học...</h3></Card> : null}
            {error ? <Card className="recent-course"><h3>{error}</h3></Card> : null}
            {!loading && !error && featuredCourses.slice(0, 5).map((course) => (
              <FeaturedCourseCard
                key={course.id}
                course={course}
                deleting={deletingId === course.id}
                onDelete={handleDeleteCourse}
                onConfig={(c) => setConfigCourseId(c.id)}
              />
            ))}
            {!loading && !error && !featuredCourses.length ? <Card className="recent-course"><h3>Chưa có môn học nào.</h3></Card> : null}
          </div>
        </section>

        <section className="course-section">
          <div className="course-section-head">
            <div>
              <h2>Thư viện của bạn</h2>
              <p className="course-section-copy">Lướt nhanh tất cả môn đang theo dõi và mở lại đúng chỗ cần làm việc tiếp.</p>
            </div>
          </div>
          <div className="recent-grid">
            <Card className="create-course-card" as="button" onClick={() => navigate("/courses/new")}>
              <span><Plus size={24} /></span>
              <strong>Tạo môn học mới</strong>
            </Card>
            {!loading && !error && visibleRecentCourses.slice(0, 6).map((course) => (
              <RecentCourseCard
                key={course.id}
                course={course}
                deleting={deletingId === course.id}
                onDelete={handleDeleteCourse}
                onConfig={(c) => setConfigCourseId(c.id)}
              />
            ))}
          </div>
        </section>
      </PageContainer>

      <CourseConfigModal
        open={Boolean(configCourseId)}
        courseId={configCourseId}
        onClose={() => setConfigCourseId(null)}
        onSaveSuccess={loadCourses}
      />
    </AppShell>
  );
}
