import { useEffect, useMemo, useState } from "react";
import { AlertCircle, BookMarked, ChevronRight, ChevronsRight, FileQuestion, Gauge, Loader2, RotateCcw, Sparkles } from "lucide-react";
import { Button, Modal } from "../../components/common.jsx";

const studioActions = [
  { title: "Tạo quiz", text: "Sinh câu hỏi từ nguồn đã chọn.", icon: FileQuestion, tone: "green", action: "quiz" },
  { title: "Tạo flashcard", text: "Sinh thẻ nhớ từ tài liệu.", icon: BookMarked, tone: "amber", action: "flashcards" }
];

export function StudioPanel({
  output, syllabus, topics = [], quizHistory, flashcardHistory,
  onGenerateQuiz, onGenerateFlashcards, onOpenQuiz, onOpenFlashcards,
  onToggleCollapsed, activeTopicId, activeTask, className = ""
}) {
  const currentTopicId = activeTask?.topicId || activeTopicId;
  const currentTopic = topics.find((t) => t.id === currentTopicId);

  const filteredQuizHistory = currentTopicId
    ? quizHistory.filter((q) => q.topicId === currentTopicId)
    : quizHistory;

  const filteredFlashcards = currentTopicId
    ? flashcardHistory.filter((f) => f.topicId === currentTopicId)
    : flashcardHistory;

  const visibleFlashcards = filteredFlashcards.slice(0, 8);

  return (
    <aside className={`studio-panel ${className}`.trim()}>
      <div className="studio-head">
        <h2>Quiz & Flashcard</h2>
        {onToggleCollapsed ? (
          <button type="button" className="sidebar-toggle-btn" onClick={onToggleCollapsed} aria-label="Đóng panel studio" title="Đóng panel studio">
            <ChevronsRight size={18} />
          </button>
        ) : null}
      </div>
      <div className="studio-banner">
        <Sparkles size={18} />
        <span>Tạo nội dung học từ tài liệu đã parse.</span>
      </div>

      {currentTopic && (
        <div className="studio-current-topic-banner">
          <span>Chủ đề đang ôn tập:</span>
          <strong>{currentTopic.title}</strong>
        </div>
      )}

      <div className="studio-grid">
        {studioActions.map((action) => {
          const Icon = action.icon;
          const handleClick = action.action === "quiz" ? onGenerateQuiz : action.action === "flashcards" ? onGenerateFlashcards : undefined;
          return <button key={action.title} type="button" className={`studio-card tone-${action.tone}`} onClick={handleClick}><span><Icon size={21} /></span><strong>{action.title}</strong><small>{action.text}</small></button>;
        })}
      </div>
      <div className="studio-output">
        <h3>Vừa tạo</h3>
        {output ? <button type="button" onClick={output.action}><FileQuestion size={20} /><span><strong>{output.title}</strong><small>{output.subtitle}</small></span><ChevronRight size={18} /></button> : <p className="empty-copy">Chưa có đầu ra mới.</p>}
      </div>
      <div className="studio-output">
        <h3>Lịch sử quiz</h3>
        {filteredQuizHistory.length ? filteredQuizHistory.slice(0, 6).map((quiz) => (
          <button type="button" key={quiz.id} onClick={() => onOpenQuiz(quiz)}>
            <FileQuestion size={20} />
            <span>
              <strong>{quiz.title}</strong>
              <small>{quiz.questions?.length || 0} câu hỏi · {new Date(quiz.createdAt).toLocaleString("vi-VN")}</small>
            </span>
            <ChevronRight size={18} />
          </button>
        )) : <p className="empty-copy">Chưa có quiz nào cho chủ đề này. Hãy nhấn "Tạo quiz" để bắt đầu.</p>}
      </div>
      <div className="studio-output">
        <h3>Lịch sử flashcard</h3>
        {visibleFlashcards.length ? visibleFlashcards.map((card, index) => (
          <button type="button" key={card.id} onClick={() => onOpenFlashcards(visibleFlashcards, index)}>
            <BookMarked size={20} />
            <span>
              <strong>{card.front}</strong>
              <small>{card.sourceRef?.filename || "Nguồn học"} · {card.createdAt ? new Date(card.createdAt).toLocaleString("vi-VN") : "Đã tạo"}</small>
            </span>
            <ChevronRight size={18} />
          </button>
        )) : <p className="empty-copy">Chưa có flashcard nào cho chủ đề này. Hãy nhấn "Tạo flashcard" để bắt đầu.</p>}
      </div>
    </aside>
  );
}

export function SelfAssessmentModal({ open, topics = [], busy, onClose, onSubmit }) {
  const eligibleTopics = useMemo(() => topics.filter((topic) => topic.practiceAllowed && ["taught", "current"].includes(topic.learningState || "taught")), [topics]);
  const [scores, setScores] = useState({});

  useEffect(() => {
    if (!open) return;
    setScores(Object.fromEntries(eligibleTopics.map((topic) => [topic.id, Math.round((topic.masteryPercent ?? 0) / 10)])));
  }, [eligibleTopics, open]);

  const submit = () => onSubmit(eligibleTopics.map((topic) => ({ topicId: topic.id, score: Number(scores[topic.id] ?? 0) })));

  return (
    <Modal
      title="Tự đánh giá topic"
      open={open}
      onClose={onClose}
      className="self-assessment-shell"
      footer={<><span className="quiz-setup-source-count">{eligibleTopics.length} topic có thể đánh giá</span><Button variant="primary" onClick={submit} disabled={busy || !eligibleTopics.length}>{busy ? "Đang lưu..." : "Lưu đánh giá"}</Button></>}
    >
      <div className="self-assessment-list">
        {eligibleTopics.map((topic) => {
          const value = Number(scores[topic.id] ?? 0);
          return (
            <label className="self-assessment-row" key={topic.id}>
              <span><strong>{topic.title || topic.name}</strong><small>Mastery {topic.masteryPercent ?? 0}% · Tin cậy {topic.confidencePercent ?? 0}%</small></span>
              <input type="range" min="0" max="10" value={value} onChange={(event) => setScores((items) => ({ ...items, [topic.id]: event.target.value }))} disabled={busy} />
              <input type="number" min="0" max="10" value={value} onChange={(event) => setScores((items) => ({ ...items, [topic.id]: Math.max(0, Math.min(10, Number(event.target.value || 0))) }))} disabled={busy} />
            </label>
          );
        })}
        {!eligibleTopics.length ? <p className="empty-copy">Chưa có topic đã học hoặc đang học để tự đánh giá.</p> : null}
      </div>
    </Modal>
  );
}

export function GenerationStatusPanel({ job, onRetry, onToggleCollapsed, className = "" }) {
  const isError = job?.status === "error";
  const isQuiz = job?.type === "quiz";
  const isCourseSetup = job?.type === "course-setup";
  const Icon = isError ? AlertCircle : Loader2;
  const numericProgress = Number(job?.progress);
  const hasProgress = Number.isFinite(numericProgress);
  const progress = Math.max(5, Math.min(100, hasProgress ? numericProgress : 42));
  const title = job?.title || (isQuiz ? "Đang tạo quiz" : "Đang tạo flashcard");
  const subtitle = job?.subtitle || "Bạn có thể tiếp tục học trong lúc chờ.";

  return (
    <aside className={`studio-panel generation-status-panel ${className}`.trim()}>
      <div className="studio-head">
        <h2>{isCourseSetup ? "Tài liệu" : isQuiz ? "Quiz" : "Flashcard"}</h2>
        {onToggleCollapsed ? (
          <button type="button" className="sidebar-toggle-btn" onClick={onToggleCollapsed} aria-label="Ẩn panel tạo nội dung" title="Ẩn panel tạo nội dung">
            <ChevronsRight size={18} />
          </button>
        ) : null}
      </div>
      <div className={`generation-status-card ${isError ? "is-error" : "is-loading"}`}>
        <div className="generation-status-icon"><Icon size={24} /></div>
        <span>{isError ? "Cần thử lại" : "Đang xử lý"}</span>
        <h3>{title}</h3>
        <p>{isError ? job?.error || subtitle : subtitle}</p>
        {!isError ? <div className={`generation-progress-line ${hasProgress ? "is-determinate" : ""}`} aria-label={hasProgress ? `${Math.round(progress)}%` : "Đang xử lý"}><span style={hasProgress ? { width: `${progress}%` } : undefined} /></div> : null}
        {!isError && hasProgress ? <small>{Math.round(progress)}%{job?.readySourceCount !== undefined ? ` - ${job.readySourceCount}/${Math.max(job.sourceCount || 0, job.readySourceCount)} tài liệu sẵn sàng` : ""}</small> : null}
        {isError ? <Button variant="primary" icon={RotateCcw} onClick={onRetry}>Thử lại</Button> : <small>Bạn có thể tiếp tục chat, xem tài liệu hoặc đổi tab.</small>}
      </div>
    </aside>
  );
}
