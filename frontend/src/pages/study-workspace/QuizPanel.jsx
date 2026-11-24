import { useState } from "react";
import { ArrowLeft, ChevronsRight, MessageSquare, Sparkles } from "lucide-react";
import { Button, Modal } from "../../components/common.jsx";
import { CitationChip } from "./ConversationPanel.jsx";

export function QuizSetupModal({ open, onClose, onSubmit, busy, selectedCount }) {
  const [countMode, setCountMode] = useState("20");
  const [customCount, setCustomCount] = useState(20);
  const [difficulty, setDifficulty] = useState("medium");
  const [instructions, setInstructions] = useState("");

  const count = countMode === "custom" ? Math.max(1, Math.min(50, Number(customCount || 20))) : Number(countMode);

  const submit = async () => {
    await onSubmit({ count, difficulty, instructions: instructions.trim() });
  };

  return (
    <Modal
      title="Tùy chỉnh Bài kiểm tra"
      open={open}
      onClose={onClose}
      className="quiz-setup-shell"
      footer={
        <>
          <div className="quiz-setup-source-count">{selectedCount ? `${selectedCount} nguồn đang chọn` : "Dùng toàn bộ nguồn"}</div>
          <Button variant="primary" onClick={submit} disabled={busy}>{busy ? "Đang tạo..." : "Tạo"}</Button>
        </>
      }
    >
      <div className="quiz-setup-modal">
        <section>
          <h3>Số lượng câu hỏi</h3>
          <div className="quiz-setup-pills">
            {[
              ["10", "Ít hơn"],
              ["20", "Tiêu chuẩn"],
              ["30", "Nhiều hơn"],
              ["custom", "Tùy chọn"]
            ].map(([value, label]) => (
              <button key={value} type="button" className={countMode === value ? "active" : ""} onClick={() => setCountMode(value)} disabled={busy}>
                {countMode === value ? "✓ " : ""}{label}{value === "20" ? " (Mặc định)" : ""}
              </button>
            ))}
          </div>
          {countMode === "custom" ? (
            <label className="quiz-setup-custom">
              <span>Số câu</span>
              <input type="number" min="1" max="50" value={customCount} onChange={(event) => setCustomCount(event.target.value)} disabled={busy} />
            </label>
          ) : null}
        </section>

        <section>
          <h3>Độ khó</h3>
          <div className="quiz-setup-pills">
            {[
              ["easy", "Dễ"],
              ["medium", "Trung bình"],
              ["hard", "Khó"]
            ].map(([value, label]) => (
              <button key={value} type="button" className={difficulty === value ? "active" : ""} onClick={() => setDifficulty(value)} disabled={busy}>
                {difficulty === value ? "✓ " : ""}{label}{value === "medium" ? " (Mặc định)" : ""}
              </button>
            ))}
          </div>
        </section>

        <label className="quiz-setup-instructions">
          <span>Chủ đề nên là gì?</span>
          <textarea
            rows="6"
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
            placeholder={"Những điều nên thử\n• Tạo một bài kiểm tra bao quát toàn bộ nguồn đang chọn\n• Tập trung vào các khái niệm chính và mối liên hệ giữa chúng\n• Có thể yêu cầu số câu, phạm vi, hoặc kiểu câu hỏi cụ thể"}
            disabled={busy}
          />
        </label>
      </div>
    </Modal>
  );
}

export function QuizSidebarPanel({ quiz, answers, result, busy, explainBusy, questionIndex, onAnswer, onSubmit, onBack, onPreviousQuestion, onNextQuestion, onJumpQuestion, onExplainQuestion, onNextQuiz, onToggleCollapsed, className = "" }) {
  const questions = quiz?.questions || [];
  const currentQuestion = questions[questionIndex];
  const answeredCount = questions.filter((question) => answers[question.id]).length;
  const progress = questions.length ? Math.round((answeredCount / questions.length) * 100) : 0;
  const selected = currentQuestion ? answers[currentQuestion.id] : "";
  const correctAnswer = currentQuestion?.correctAnswer || currentQuestion?.answer;
  const wrongQuestionIds = new Set((result?.mistakes || []).map((mistake) => mistake.questionId));
  const isFirstQuestion = questionIndex <= 0;
  const isLastQuestion = questionIndex >= questions.length - 1;

  return (
    <aside className={`studio-panel quiz-sidebar-panel ${className}`.trim()}>
      <div className="quiz-sidebar-top">
        <button type="button" className="quiz-back-btn" onClick={onBack} disabled={busy}>
          <ArrowLeft size={16} />
          <span>Quay lại</span>
        </button>
        <button type="button" className="quiz-next-btn" onClick={onNextQuiz} disabled={busy}>
          <Sparkles size={15} />
          <span>Quiz tiếp theo</span>
        </button>
        {onToggleCollapsed ? (
          <button type="button" className="sidebar-toggle-btn" onClick={onToggleCollapsed} aria-label="Đóng panel quiz" title="Đóng panel quiz">
            <ChevronsRight size={18} />
          </button>
        ) : null}
      </div>

      <div className="quiz-hero">
        <span>Quiz luyện tập</span>
        <h2>{quiz?.title || "Quiz"}</h2>
        <div className="quiz-progress-line">
          <strong>{result ? `${result.score}/${result.total} đúng` : `Câu ${questionIndex + 1}/${questions.length}`}</strong>
          <small>{result ? `${result.accuracyPercent}%` : `${answeredCount}/${questions.length} đã chọn`}</small>
        </div>
        <div className="quiz-progress-track"><span style={{ width: `${result ? result.accuracyPercent : progress}%` }} /></div>
      </div>

      {result ? (
        <div className="quiz-result-summary">
          <div>
            <span>Điểm tổng</span>
            <strong>{result.score}/{result.total}</strong>
            <small>{result.accuracyPercent}% chính xác</small>
          </div>
          <div className="quiz-result-grid">
            {questions.map((question, index) => {
              const isCorrect = !wrongQuestionIds.has(question.id);
              return (
                <button key={question.id} type="button" className={`${isCorrect ? "is-correct" : "is-wrong"} ${index === questionIndex ? "active" : ""}`} onClick={() => onJumpQuestion(index)}>
                  {index + 1}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {currentQuestion ? (
        <div className="quiz-focus-card">
          <div className="quiz-focus-index">Câu hỏi {questionIndex + 1}</div>
          <h3>{currentQuestion.question || currentQuestion.prompt}</h3>
          <div className="quiz-options quiz-options-sidebar">
            {(currentQuestion.options || currentQuestion.choices || []).map((option) => {
              const isCorrect = result && option === correctAnswer;
              const isWrong = result && selected === option && option !== correctAnswer;
              return (
                <label key={option} className={`${selected === option ? "selected" : ""} ${isCorrect ? "is-correct-option" : ""} ${isWrong ? "is-wrong-option" : ""}`}>
                  <input type="radio" name={currentQuestion.id} value={option} checked={selected === option} disabled={Boolean(result)} onChange={() => onAnswer(currentQuestion.id, option)} />
                  <span>{option}</span>
                </label>
              );
            })}
          </div>

          {result ? (
            <div className="quiz-explanation">
              <strong>Đáp án đúng: {correctAnswer}</strong>
              <p>{currentQuestion.explanation}</p>
              {currentQuestion.sourceRef ? <CitationChip sourceRef={currentQuestion.sourceRef} index={questionIndex} /> : null}
              <button type="button" className="quiz-explain-btn" onClick={() => onExplainQuestion(currentQuestion, questionIndex)} disabled={explainBusy}>
                <MessageSquare size={15} />
                <span>{explainBusy ? "Đang gửi..." : "Giải thích"}</span>
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="quiz-sidebar-actions">
        {!result ? (
          <>
            <Button variant="secondary" onClick={onPreviousQuestion} disabled={busy || isFirstQuestion}>Câu trước</Button>
            {isLastQuestion ? (
              <Button variant="primary" onClick={onSubmit} disabled={busy || !questions.length || !selected}>{busy ? "Đang nộp..." : "Nộp bài"}</Button>
            ) : (
              <Button variant="primary" onClick={onNextQuestion} disabled={busy || !selected}>Câu tiếp</Button>
            )}
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onBack}>Xem Studio</Button>
            <Button variant="primary" onClick={onNextQuiz} disabled={busy}>{busy ? "Đang tạo..." : "Quiz tiếp theo"}</Button>
          </>
        )}
      </div>
    </aside>
  );
}
