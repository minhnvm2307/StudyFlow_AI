export function buildCourseDetailQuizPayload({
  courseId,
  topicId,
  count,
  difficulty,
  instructions = "",
}) {
  const normalizedInstructions = String(instructions || "").trim();

  return {
    courseId,
    count,
    difficulty,
    query: normalizedInstructions,
    instructions: normalizedInstructions,
    selectedSourceIds: [],
    topicIds: [topicId],
  };
}

export function buildCourseDetailWorkspacePath({
  courseId,
  topicId = "",
  taskId = "",
  returnTo = "",
}) {
  const params = new URLSearchParams();
  if (taskId) {
    params.set("task", taskId);
  } else if (topicId) {
    params.set("topic", topicId);
  }
  if (returnTo) {
    params.set("returnTo", returnTo);
  }
  const query = params.toString();
  return `/study/${courseId}${query ? `?${query}` : ""}`;
}

export function buildCourseDetailQuizWorkspacePath(courseId, topicId) {
  return buildCourseDetailWorkspacePath({ courseId, topicId });
}
