export function sortFlashcards(cards) {
  return [...cards].sort((a, b) => new Date(b.createdAt || b.dueAt || 0) - new Date(a.createdAt || a.dueAt || 0));
}

export function createQuizExplainPayload({ activeQuiz, question, index, quizAnswers }) {
  const selectedAnswer = quizAnswers[question.id] || "Chưa chọn";
  const correctAnswer = question.correctAnswer || question.answer;
  const source = question.sourceRef;
  const message = [
    `Giải thích sâu hơn câu quiz số ${index + 1}: ${question.question || question.prompt}`,
    `Mình đã chọn: ${selectedAnswer}`,
    `Đáp án đúng: ${correctAnswer}`,
    question.explanation ? `Giải thích ngắn hiện tại: ${question.explanation}` : "",
    source ? `Nguồn: ${source.filename || "nguồn học"}${source.page ? ` trang ${source.page}` : ""}${source.section ? `, ${source.section}` : ""}` : ""
  ].filter(Boolean).join("\n");

  return {
    message,
    context: {
      type: "quiz_mistake",
      quizId: activeQuiz.id,
      questionId: question.id,
      question: question.question || question.prompt,
      selectedAnswer,
      correctAnswer,
      explanation: question.explanation,
      sourceRef: source
    }
  };
}
