import { useEffect, useMemo, useState } from "react";
import { CalendarClock, TimerReset } from "lucide-react";
import {
  Badge,
  Button,
  AppShell,
  Card,
  PageContainer,
  SectionHeader,
  SelectButton,
  TopNav
} from "../../components/common.jsx";
import { navigate } from "../../router.jsx";
import { dashboardApi } from "../../services/studyflowApi.js";
import { getCurrentUser } from "../../services/authSession.js";
import { CourseProgressCard, FocusCard, StatsPanel, TaskCard, WeakTopicsCard, ProfileDashboardView } from "./components.jsx";

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("tasks"); // "tasks" or "profile"

  const loadData = () => {
    setLoading(true);
    dashboardApi.getDashboard()
      .then((data) => {
        setDashboard(data);
        setError("");
      })
      .catch((err) => {
        setError(err.message || "Không thể tải dashboard.");
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  const courseById = useMemo(() => new Map((dashboard?.courses || []).map((course) => [course.id, course])), [dashboard]);

  if (loading) {
    return <AppShell><TopNav active="dashboard" /><PageContainer><Card className="stack-card">Đang tải dashboard...</Card></PageContainer></AppShell>;
  }

  if (error) {
    return <AppShell><TopNav active="dashboard" /><PageContainer><Card className="stack-card">{error}</Card></PageContainer></AppShell>;
  }

  const todayMinutes = dashboard.todayTasks.reduce((sum, task) => sum + (task.durationMinutes || 0), 0);
  const user = getCurrentUser();
  const userName = user?.username || dashboard.user?.name || "bạn";

  return (
    <AppShell>
      <TopNav active="dashboard" />
      <PageContainer className="dashboard-page">
        <div className="dashboard-header">
          <div>
            <h1>Chào mừng, {userName}!</h1>
            <p>Hôm nay bạn có {dashboard.todayTasks.length} nhiệm vụ, tổng cộng {todayMinutes} phút.</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab("tasks")}
              className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all cursor-pointer ${
                activeTab === "tasks"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm"
                  : "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--muted)]"
              }`}
            >
              Nhiệm vụ & Tiến độ
            </button>
            <button
              onClick={() => setActiveTab("profile")}
              className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all cursor-pointer ${
                activeTab === "profile"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm"
                  : "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--muted)]"
              }`}
            >
              Hồ sơ Năng lực AI
            </button>
          </div>
        </div>

        <div className="dashboard-layout">
          {activeTab === "tasks" ? (
            <div className="dashboard-main">
              <FocusCard task={dashboard.nextSchedule || dashboard.todayTasks[0]} courseById={courseById} />

              <SectionHeader title="Nhiệm vụ hôm nay" action={<span className="section-meta"><TimerReset size={15} /> {todayMinutes} phút</span>} />
              <div className="task-grid">
                {dashboard.todayTasks.length ? dashboard.todayTasks.map((task) => <TaskCard key={task.id} task={task} courseById={courseById} />) : (
                  <Card className="task-card"><h3>Không có nhiệm vụ hôm nay</h3><p>Tạo kế hoạch học để bắt đầu.</p></Card>
                )}
              </div>

              <div className="dashboard-two-col">
                <CourseProgressCard courses={dashboard.courses} />
                <WeakTopicsCard topics={dashboard.weakTopics} courseById={courseById} />
              </div>

              <Card className="due-strip">
                <div>
                  <Badge tone="amber">Cần ôn tập</Badge>
                  <h3>{dashboard.missedTasks?.length || 0} nhiệm vụ cần xử lý lại</h3>
                  <p>Lập lại lịch nếu bạn đã bỏ lỡ nhiệm vụ hoặc cần đổi cường độ học.</p>
                </div>
                <div className="due-actions">
                  <Button variant="primary" onClick={() => navigate("/schedule")}>Lập lại lịch</Button>
                  <Button variant="secondary" icon={CalendarClock} onClick={() => navigate("/schedule")}>Xem lịch</Button>
                </div>
              </Card>
            </div>
          ) : (
            <div className="dashboard-main">
              <ProfileDashboardView dashboard={dashboard} />
            </div>
          )}
          <StatsPanel dashboard={dashboard} courseById={courseById} />
        </div>
      </PageContainer>
    </AppShell>
  );
}

