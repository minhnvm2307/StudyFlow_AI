import { useEffect, useMemo, useState } from "react";
import DashboardPage from "./pages/dashboard/index.jsx";
import CoursesPage from "./pages/courses/index.jsx";
import SchedulePage from "./pages/schedule/index.jsx";
import StudyWorkspacePage from "./pages/study-workspace/index.jsx";
import OnboardingCoursePage from "./pages/onboarding-course/index.jsx";
import CourseDetailPage from "./pages/course-detail/index.jsx";
import LoginPage from "./pages/login/index.jsx";
import LandingPage from "./pages/landing/index.jsx";
import { getCurrentUser, onAuthChange } from "./services/authSession.js";
import { navigate } from "./router.jsx";

function normalizePath(pathname) {
  if (pathname === "/") return "/";
  return pathname.replace(/\/+$/, "");
}

function routeFor(pathname) {
  const path = normalizePath(pathname);
  if (path === "/login") return "login";
  if (path === "/" || path === "/landing") return "landing";
  if (path === "/dashboard") return "dashboard";
  if (path === "/courses") return "courses";
  if (path === "/courses/new") return "course-new";
  if (path.startsWith("/courses/detail/")) return "course-detail";
  if (path === "/schedule") return "schedule";
  if (path.startsWith("/study/")) return "study";
  return "dashboard";
}

export default function App() {
  const [path, setPath] = useState(() => normalizePath(window.location.pathname));
  const [currentUser, setCurrentUser] = useState(() => getCurrentUser());

  useEffect(() => {
    const handlePopState = () => setPath(normalizePath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => onAuthChange(setCurrentUser), []);

  useEffect(() => {
    if (!currentUser && path !== "/login" && path !== "/" && path !== "/landing") {
      navigate("/");
    }
    if (currentUser && (path === "/login" || path === "/" || path === "/landing")) navigate("/dashboard");
  }, [currentUser, path]);

  const route = useMemo(() => routeFor(path), [path]);
  const effectiveRoute = currentUser
    ? ((route === "login" || route === "landing") ? "dashboard" : route)
    : (route === "login" ? "login" : "landing");

  return (
    <>
      <div className="viewport-warning">
        Giao diện prototype này tối ưu cho browser từ 1024px trở lên. Một số vùng như lịch tuần và workspace có thể cuộn ngang trên màn hình hẹp.
      </div>
      {effectiveRoute === "landing" && <LandingPage />}
      {effectiveRoute === "login" && <LoginPage />}
      {effectiveRoute === "dashboard" && <DashboardPage activePath={path} />}
      {effectiveRoute === "courses" && <CoursesPage activePath={path} />}
      {effectiveRoute === "course-new" && <OnboardingCoursePage />}
      {effectiveRoute === "course-detail" && <CourseDetailPage />}
      {effectiveRoute === "schedule" && <SchedulePage activePath={path} />}
      {effectiveRoute === "study" && <StudyWorkspacePage activePath={path} />}
    </>
  );
}
