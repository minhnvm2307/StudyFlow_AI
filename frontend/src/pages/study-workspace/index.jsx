import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle, Loader2, Sparkles, BookOpen, Calendar, HelpCircle } from "lucide-react";
import { Card } from "../../components/common.jsx";
import { AddSourceModal } from "./AddSourceDialog.jsx";
import { ConversationPanel } from "./ConversationPanel.jsx";
import { FlashcardPracticeModal } from "./PracticeModals.jsx";
import { QuizSetupModal, QuizSidebarPanel } from "./QuizPanel.jsx";
import { WorkspaceLeftSidebar, WorkspaceSideRail } from "./SourcesPanel.jsx";
import { GenerationStatusPanel, SelfAssessmentModal, StudioPanel } from "./StudioPanel.jsx";
import { useStudyWorkspace } from "./useStudyWorkspace.js";
import { useWorkspaceResize } from "./useWorkspaceResize.js";
import { WorkspaceTopBar } from "./WorkspaceTopBar.jsx";
import { buildLegacySetupRedirectPath } from "./navigation.js";
import { navigate } from "../../router.jsx";

const SYSTEM_HINTS = [
  {
    title: "Hỏi đáp tài liệu thông minh (Chat RAG)",
    description: "Hệ thống RAG tự động phân tích sâu giáo trình và tài liệu của bạn để trả lời các câu hỏi chi tiết về định nghĩa, công thức hoặc so sánh."
  },
  {
    title: "Luyện tập thông minh (Quiz & Flashcard)",
    description: "Các câu hỏi trắc nghiệm và thẻ ghi nhớ Flashcard được tạo tự động dựa trên thuật toán Spaced Repetition (Lặp lại ngắt quãng FSRS) giúp bạn ghi nhớ hiệu quả gấp 3 lần."
  },
  {
    title: "Tối ưu hóa lịch học cá nhân",
    description: "Hệ thống sẽ tự động phân bổ khối lượng kiến thức vào các ngày rảnh trong tuần dựa trên thời gian mong muốn của bạn."
  },
  {
    title: "Học tập có mục tiêu",
    description: "Bạn có thể thiết lập điểm số mục tiêu cho môn học. AI sẽ ưu tiên gợi ý các chủ đề bạn còn yếu để bù lấp lỗ hổng kiến thức trước ngày thi."
  }
];

function SetupLoadingPage({ courseName, courseId, job, syllabus, onCancel }) {
  const [hintIndex, setHintIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setHintIndex((prev) => (prev + 1) % SYSTEM_HINTS.length);
    }, 6000);
    return () => clearInterval(timer);
  }, []);

  const activeHint = SYSTEM_HINTS[hintIndex];

  const syllabusProgress = job.syllabus || { status: "processing", percent: 0 };
  const practice = job.practice || { status: "pending", percent: 0 };
  const schedule = job.schedule || { status: "pending", percent: 0 };
  const syllabusStatusText = syllabusProgress.status === "completed"
    ? "Đã trích xuất bài học và cấu trúc môn học."
    : syllabusProgress.status === "failed"
      ? (job.error || syllabusProgress.message || "Không thể phân tích giáo trình và tài liệu.")
      : "Đang đọc tài liệu...";
  const scheduleStatusText = schedule.status === "completed"
    ? "Lịch học đã sẵn sàng trên Calendar."
    : schedule.status === "failed"
      ? (schedule.message || "Đã dừng do lỗi trước khi tối ưu lịch học.")
      : schedule.status === "generating"
        ? "Đang sắp xếp lịch học tối ưu..."
        : "Chờ phân tích xong tài liệu...";
  const practiceStatusText = practice.status === "completed"
    ? "Đã tạo xong quiz và flashcards cho các chủ đề."
    : practice.status === "failed"
      ? (practice.message || "Đã dừng do lỗi trước khi tạo quiz và flashcards.")
      : practice.status === "generating"
        ? "Đang sinh câu hỏi luyện tập tự động..."
        : "Chờ sắp xếp lịch học...";

  const handleGoToCalendar = () => {
    sessionStorage.setItem("studyflow.newCourseId", courseId);
    navigate("/schedule");
  };

  const renderStatusIcon = (status) => {
    if (status === "completed") {
      return <CheckCircle2 className="status-icon text-green" size={20} />;
    }
    if (status === "failed") {
      return <AlertCircle className="status-icon text-red" size={20} />;
    }
    if (status === "generating" || status === "processing") {
      return <Loader2 className="status-icon animate-spin text-primary" size={20} />;
    }
    return <div className="status-icon-dot" />;
  };

  const hasExtractedSyllabus = syllabus?.lessons && syllabus.lessons.length > 0;

  return (
    <div className="setup-loading-screen">
      <div className="setup-loading-card">
        <div className="setup-loading-header">
          <Sparkles className="header-sparkle animate-pulse" size={32} />
          <h2>Đang thiết lập môn học</h2>
          <h1>{courseName}</h1>
          <p className="setup-loading-subtitle">{job.subtitle || "Hệ thống AI đang xử lý tài liệu và cá nhân hóa lịch học của bạn..."}</p>
        </div>

        <div className="setup-loading-progress-section">
          {/* Syllabus Progress */}
          <div className={`progress-bar-group ${syllabusProgress.status}`}>
            <div className="progress-bar-header">
              <span className="flex items-center gap-2" style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                <BookOpen size={16} />
                <strong>1. Đọc và phân tích giáo trình & tài liệu</strong>
              </span>
              <span className="progress-percent">
                {syllabusProgress.status === "completed" ? "Hoàn thành" : `${syllabusProgress.percent}%`}
              </span>
            </div>
            <div className="progress-bar-track">
              <div className="progress-bar-fill" style={{ width: `${syllabusProgress.percent}%` }} />
            </div>
            <div className="progress-status-container">
              {renderStatusIcon(syllabusProgress.status)}
              <span className="progress-status-text">{syllabusStatusText}</span>
            </div>
          </div>

          {/* Schedule Progress */}
          <div className={`progress-bar-group ${schedule.status}`}>
            <div className="progress-bar-header">
              <span className="flex items-center gap-2" style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                <Calendar size={16} />
                <strong>2. Tối ưu hóa lịch trình học tập cá nhân</strong>
              </span>
              <span className="progress-percent">
                {schedule.status === "completed" ? "Hoàn thành" : schedule.status === "pending" ? "Đang chờ" : `${schedule.percent}%`}
              </span>
            </div>
            <div className="progress-bar-track">
              <div className="progress-bar-fill" style={{ width: `${schedule.percent}%` }} />
            </div>
            <div className="progress-status-container">
              {renderStatusIcon(schedule.status)}
              <span className="progress-status-text">{scheduleStatusText}</span>
            </div>
          </div>

          {/* Practice Progress */}
          <div className={`progress-bar-group ${practice.status}`}>
            <div className="progress-bar-header">
              <span className="flex items-center gap-2" style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                <HelpCircle size={16} />
                <strong>3. Tạo bộ câu hỏi trắc nghiệm & thẻ Flashcard</strong>
              </span>
              <span className="progress-percent">
                {practice.status === "completed" ? "Hoàn thành" : practice.status === "pending" ? "Đang chờ" : `${practice.percent}%`}
              </span>
            </div>
            <div className="progress-bar-track">
              <div className="progress-bar-fill" style={{ width: `${practice.percent}%` }} />
            </div>
            <div className="progress-status-container">
              {renderStatusIcon(practice.status)}
              <span className="progress-status-text">{practiceStatusText}</span>
            </div>
          </div>
        </div>

        {/* Redirect Button */}
        {syllabusProgress.status === "completed" || schedule.status === "completed" ? (
          <div className="setup-loading-actions animate-fade-in" style={{ display: "flex", justifyContent: "center" }}>
            <button className="btn-primary-large" onClick={handleGoToCalendar}>
              Xem lịch học của bạn ngay <Calendar size={18} style={{ marginLeft: "8px" }} />
            </button>
          </div>
        ) : job.status === "error" ? (
          <div className="setup-loading-actions error-actions">
            <p className="error-msg">{job.error || "Có lỗi xảy ra trong quá trình thiết lập."}</p>
            <button className="btn-secondary" onClick={onCancel}>
              Quay lại Dashboard
            </button>
          </div>
        ) : (
          <div className="setup-loading-footer">
            <button className="btn-cancel" onClick={onCancel}>
              Hủy thiết lập & Quay lại
            </button>
          </div>
        )}
      </div>

      {/* Extracted Syllabus or System Hints Section */}
      <div className="setup-hints-card" style={{ display: "flex", flexDirection: "column", minWidth: "320px", maxWidth: "420px" }}>
        {hasExtractedSyllabus ? (
          <>
            <div className="hint-label" style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.1)", paddingBottom: "12px", marginBottom: "16px" }}>CẤU TRÚC MÔN HỌC ĐÃ TRÍCH XUẤT</div>
            <div className="extracted-syllabus-scroll" style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "10px", width: "100%", paddingRight: "4px" }}>
              {syllabus.lessons.map((lesson, idx) => (
                <div key={lesson.id || idx} className="extracted-lesson-item" style={{ padding: "12px", borderRadius: "8px", backgroundColor: "rgba(255, 255, 255, 0.04)", borderLeft: "3px solid #3b82f6", display: "flex", flexDirection: "column", gap: "4px" }}>
                  <div style={{ fontWeight: "bold", fontSize: "11px", color: "#60a5fa", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                    Tuần {lesson.weekNumber || lesson.lessonNumber || (idx + 1)}
                  </div>
                  <div style={{ fontSize: "13px", fontWeight: "600", color: "#f3f4f6", lineHeight: "1.4" }}>
                    {lesson.title}
                  </div>
                  {lesson.description && (
                    <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px", lineHeight: "1.4" }}>
                      {lesson.description}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        ) : (
          <>
            <div className="hint-label">HỢI Ý TỪ HỆ THỐNG AI</div>
            <div className="hint-content animate-fade-in" key={hintIndex}>
              <h3>{activeHint.title}</h3>
              <p>{activeHint.description}</p>
            </div>
            <div className="hint-dots">
              {SYSTEM_HINTS.map((_, idx) => (
                <div key={idx} className={`hint-dot ${idx === hintIndex ? "active" : ""}`} onClick={() => setHintIndex(idx)} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StudyWorkspaceContent() {
  const workspace = useStudyWorkspace();
  const resize = useWorkspaceResize();
  const quizInProgress = Boolean(workspace.activeQuiz && !workspace.quizResult);
  const isPracticeActive = quizInProgress || Boolean(workspace.activeFlashcards && workspace.activeFlashcards.length > 0);

  const startQuizGeneration = (payload) => {
    workspace.generateQuiz(payload);
  };

  const startFlashcardGeneration = () => {
    workspace.generateFlashcards();
  };

  if (workspace.error) {
    return <div className="workspace-shell"><WorkspaceTopBar course={workspace.course} sourceCount={0} /><div className="workspace-scroll"><Card className="stack-card">{workspace.error}</Card></div></div>;
  }

  if (workspace.generationJob?.type === "course-setup") {
    return (
      <SetupLoadingPage
        courseName={workspace.course?.name || "Môn học"}
        courseId={workspace.course?.id}
        job={workspace.generationJob}
        syllabus={workspace.syllabus}
        onCancel={() => navigate("/dashboard")}
      />
    );
  }

  return (
    <div
      className="workspace-shell"
      style={{
        "--left-sidebar-width": resize.leftCollapsed ? "64px" : `${resize.leftWidth}px`,
        "--right-sidebar-width": isPracticeActive ? "0px" : (resize.rightCollapsed ? "64px" : `${resize.rightWidth}px`),
        "--left-resizer-width": resize.leftCollapsed ? "0px" : "8px",
        "--right-resizer-width": isPracticeActive ? "0px" : (resize.rightCollapsed ? "0px" : "8px")
      }}
    >
      <WorkspaceTopBar course={workspace.course} sourceCount={workspace.sources.length} />
      <div className="workspace-scroll">
        <div className="workspace-layout">
          <WorkspaceLeftSidebar
            sources={workspace.sources}
            syllabus={workspace.syllabus}
            setupJob={workspace.generationJob?.type === "course-setup" ? workspace.generationJob : null}
            syllabusError={workspace.syllabusError}
            topics={workspace.topics}
            quizzes={workspace.quizHistory}
            threads={workspace.threads}
            activeThreadId={workspace.activeThreadId}
            onSelectThread={workspace.selectThread}
            onNewChat={workspace.startNewChat}
            onToggleSource={workspace.toggleSource}
            onAddSource={workspace.openAddSource}
            onDeleteSource={workspace.deleteSource}
            onUploadSyllabus={workspace.uploadSyllabus}
            onRetryUploadedSyllabus={workspace.retryUploadedSyllabus}
            onCreateSyllabusFromSources={workspace.createSyllabusFromSources}
            deletingSourceId={workspace.deletingSourceId}
            uploadingSyllabus={workspace.uploadingSyllabus}
            collapsed={resize.leftCollapsed}
            onToggleCollapsed={() => resize.setLeftCollapsed((value) => !value)}
            chunks={workspace.chunks}
            tasks={workspace.tasks}
            activeTask={workspace.activeTask}
            setActiveTask={workspace.setActiveTask}
            selectedTopicIds={workspace.selectedTopicIds}
            toggleTopic={workspace.toggleTopic}
            activeTopicId={workspace.activeTopicId}
            setActiveTopicId={workspace.setActiveTopicId}
            quizInProgress={isPracticeActive}
          />
          <div className={`workspace-resizer left-resizer ${resize.leftCollapsed ? "collapsed" : ""}`} role="separator" aria-label="Kéo giãn panel nguồn" aria-orientation="vertical" onPointerDown={resize.leftCollapsed ? undefined : resize.beginResize("left")} />
          
          {/* Center Stage: Quiz, Studio, or Status */}
          {workspace.generationJob ? (
            <GenerationStatusPanel
              job={workspace.generationJob}
              onRetry={workspace.retryGenerationJob}
              className="workspace-main-panel"
            />
          ) : workspace.activeQuiz ? (
            <QuizSidebarPanel
              quiz={workspace.activeQuiz}
              answers={workspace.quizAnswers}
              result={workspace.quizResult}
              busy={workspace.quizBusy}
              explainBusy={workspace.quizExplainBusy}
              questionIndex={workspace.quizQuestionIndex}
              onAnswer={workspace.answerQuiz}
              onSubmit={workspace.submitQuiz}
              onBack={workspace.closeQuiz}
              onPreviousQuestion={workspace.previousQuizQuestion}
              onNextQuestion={workspace.nextQuizQuestion}
              onJumpQuestion={workspace.setQuizQuestionIndex}
              onExplainQuestion={workspace.explainQuizQuestion}
              onNextQuiz={startQuizGeneration}
              className="workspace-main-panel"
            />
          ) : (
            <StudioPanel
              output={workspace.output}
              syllabus={workspace.syllabus}
              topics={workspace.topics}
              quizHistory={workspace.quizHistory}
              flashcardHistory={workspace.flashcardHistory}
              onGenerateQuiz={() => workspace.setQuizSetupOpen(true)}
              onGenerateFlashcards={startFlashcardGeneration}
              onOpenQuiz={workspace.openQuiz}
              onOpenFlashcards={workspace.openFlashcards}
              activeTopicId={workspace.activeTopicId}
              activeTask={workspace.activeTask}
              className="workspace-main-panel"
            />
          )}

          {!isPracticeActive && (
            <>
              <div className={`workspace-resizer right-resizer ${resize.rightCollapsed ? "collapsed" : ""}`} role="separator" aria-label="Kéo giãn panel AI chat" aria-orientation="vertical" onPointerDown={resize.rightCollapsed ? undefined : resize.beginResize("right")} />
              
              {/* Right Stage: AI chat */}
              {resize.rightCollapsed ? (
                <WorkspaceSideRail side="right" label="Mở AI chat" onToggle={() => resize.setRightCollapsed(false)} />
              ) : (
                <ConversationPanel
                  course={workspace.course}
                  sources={workspace.sources}
                  messages={workspace.messages}
                  activeThreadId={workspace.activeThreadId}
                  onSend={workspace.sendMessage}
                  sending={workspace.sending}
                  onToggleCollapsed={() => resize.setRightCollapsed(true)}
                  activeTopicId={workspace.activeTopicId}
                  topics={workspace.topics}
                  className="conversation-panel-right"
                  quizInProgress={isPracticeActive}
                  threads={workspace.threads}
                  onSelectThread={workspace.selectThread}
                  onNewChat={workspace.startNewChat}
                />
              )}
            </>
          )}
        </div>
      </div>
      <QuizSetupModal open={workspace.quizSetupOpen} onClose={() => workspace.setQuizSetupOpen(false)} onSubmit={startQuizGeneration} busy={workspace.quizBusy} selectedCount={workspace.selectedSourceIds.length} />
      <SelfAssessmentModal open={workspace.selfAssessmentOpen} topics={workspace.topics} busy={workspace.selfAssessmentBusy} onClose={() => workspace.setSelfAssessmentOpen(false)} onSubmit={workspace.submitSelfAssessment} />
      <FlashcardPracticeModal cards={workspace.activeFlashcards} index={workspace.flashcardIndex} revealed={workspace.flashcardRevealed} busy={workspace.flashcardBusy} onReveal={() => workspace.setFlashcardRevealed(true)} onRate={workspace.rateFlashcard} onNext={workspace.nextFlashcard} onClose={workspace.closeFlashcards} />
      <AddSourceModal open={workspace.addSourceOpen} onClose={() => workspace.setAddSourceOpen(false)} onSubmit={workspace.addSource} busy={workspace.addingSource} error={workspace.sourceError} />
    </div>
  );
}

export default function StudyWorkspacePage() {
  const redirectPath = buildLegacySetupRedirectPath(window.location.pathname, window.location.search);

  useEffect(() => {
    if (redirectPath) navigate(redirectPath);
  }, [redirectPath]);

  if (redirectPath) return null;

  return <StudyWorkspaceContent />;
}
