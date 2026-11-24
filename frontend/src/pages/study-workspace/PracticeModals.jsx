import { Button, Modal } from "../../components/common.jsx";
import { CitationChip } from "./ConversationPanel.jsx";

export function QuizPracticeModal({ quiz, answers, result, busy, onAnswer, onSubmit, onClose }) {
  return (
    <Modal
      title={quiz ? quiz.title : "Quiz"}
      open={Boolean(quiz)}
      onClose={busy ? undefined : onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Đóng</Button>
          {!result ? <Button variant="primary" onClick={onSubmit} disabled={busy || !quiz?.questions?.length}>{busy ? "Đang nộp..." : "Nộp bài"}</Button> : null}
        </>
      }
    >
      {quiz ? (
        <div className="practice-panel">
          <div className="practice-head">
            <strong>{quiz.questions?.length || 0} câu hỏi</strong>
            {result ? <span>{result.score}/{result.total} đúng · {result.accuracyPercent}%</span> : <span>Chọn đáp án rồi nộp bài</span>}
          </div>
          <div className="quiz-question-list">
            {quiz.questions?.map((question, index) => {
              const selected = answers[question.id];
              const correctAnswer = question.correctAnswer || question.answer;
              const isCorrect = result && selected === correctAnswer;
              const isWrong = result && selected && selected !== correctAnswer;
              return (
                <section key={question.id} className={`quiz-question ${isCorrect ? "is-correct" : ""} ${isWrong ? "is-wrong" : ""}`}>
                  <h3>{index + 1}. {question.question || question.prompt}</h3>
                  <div className="quiz-options">
                    {(question.options || question.choices || []).map((option) => (
                      <label key={option} className={selected === option ? "selected" : ""}>
                        <input type="radio" name={question.id} value={option} checked={selected === option} disabled={Boolean(result)} onChange={() => onAnswer(question.id, option)} />
                        <span>{option}</span>
                      </label>
                    ))}
                  </div>
                  {result ? (
                    <div className="quiz-explanation">
                      <strong>Đáp án đúng: {correctAnswer}</strong>
                      <p>{question.explanation}</p>
                      {question.sourceRef ? <CitationChip sourceRef={question.sourceRef} index={index} /> : null}
                    </div>
                  ) : null}
                </section>
              );
            })}
          </div>
        </div>
      ) : null}
    </Modal>
  );
}

export function FlashcardPracticeModal({ cards, index, revealed, busy, onReveal, onRate, onNext, onClose }) {
  const card = cards[index];
  return (
    <Modal
      title="Ôn flashcards"
      open={Boolean(cards.length)}
      onClose={busy ? undefined : onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Đóng</Button>
          {revealed ? <Button variant="primary" onClick={onNext} disabled={busy}>Thẻ tiếp</Button> : <Button variant="primary" onClick={onReveal} disabled={busy}>Lật thẻ</Button>}
        </>
      }
    >
      {card ? (
        <div className="practice-panel flashcard-practice">
          <div className="practice-head">
            <strong>Thẻ {index + 1}/{cards.length}</strong>
            <span>{card.sourceRef?.filename || "Nguồn học"}</span>
          </div>
          <button type="button" className={`flashcard-review-card ${revealed ? "is-revealed" : ""}`} onClick={onReveal}>
            <span>{revealed ? "Mặt sau" : "Mặt trước"}</span>
            <strong>{revealed ? card.back : card.front}</strong>
            {revealed && card.explanation ? <small>{card.explanation}</small> : null}
          </button>
          {revealed ? (
            <div className="flashcard-rating">
              {[
                ["again", "Làm lại"],
                ["hard", "Khó"],
                ["good", "Tốt"],
                ["easy", "Dễ"]
              ].map(([rating, label]) => <Button key={rating} variant="secondary" onClick={() => onRate(card, rating)} disabled={busy}>{label}</Button>)}
            </div>
          ) : null}
          {revealed && card.sourceRef ? <div className="practice-source"><CitationChip sourceRef={card.sourceRef} index={0} /></div> : null}
        </div>
      ) : null}
    </Modal>
  );
}
