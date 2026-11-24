import { ArrowLeft, BookMarked, LogOut } from "lucide-react";
import { Avatar } from "../../components/common.jsx";
import { navigate } from "../../router.jsx";
import { clearCurrentUser } from "../../services/authSession.js";
import { buildWorkspaceBackPath } from "./navigation.js";

function logout() {
  clearCurrentUser();
  navigate("/");
}

export function WorkspaceTopBar({ course, sourceCount }) {
  const backPath = buildWorkspaceBackPath(window.location.pathname, window.location.search);

  return (
    <header className="workspace-topbar">
      <div className="workspace-title">
        <button type="button" className="workspace-back" onClick={() => navigate(backPath)} aria-label="Về môn học">
          <ArrowLeft size={18} />
        </button>
        <div className="workspace-icon"><BookMarked size={20} /></div>
        <div>
          <h1>Sổ ghi chú {course?.name || "StudyFlow"}</h1>
          <p>Sổ tay học tập - {course?.currentLesson?.title || "Chưa chọn bài học trong đề cương"} - {sourceCount} tài liệu</p>
        </div>
      </div>
      <div className="workspace-actions">
        <button type="button" className="workspace-back" onClick={logout} aria-label="Đăng xuất" title="Đăng xuất">
          <LogOut size={18} />
        </button>
        <Avatar />
      </div>
    </header>
  );
}
