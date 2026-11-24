import test from "node:test";
import assert from "node:assert/strict";

import {
  buildCourseDetailQuizPayload,
  buildCourseDetailQuizWorkspacePath,
  buildCourseDetailWorkspacePath,
} from "./quizActions.js";

test("buildCourseDetailQuizPayload scopes quiz generation to the selected topic", () => {
  const payload = buildCourseDetailQuizPayload({
    courseId: "course_123",
    topicId: "topic_abc",
    count: 15,
    difficulty: "hard",
    instructions: "  Tap trung vao khai niem cot loi  ",
  });

  assert.deepEqual(payload, {
    courseId: "course_123",
    count: 15,
    difficulty: "hard",
    query: "Tap trung vao khai niem cot loi",
    instructions: "Tap trung vao khai niem cot loi",
    selectedSourceIds: [],
    topicIds: ["topic_abc"],
  });
});

test("buildCourseDetailQuizWorkspacePath deep-links back to the same topic in workspace", () => {
  assert.equal(
    buildCourseDetailQuizWorkspacePath("course_123", "topic_abc"),
    "/study/course_123?topic=topic_abc"
  );
});

test("buildCourseDetailWorkspacePath preserves the course detail return path for topic deep links", () => {
  assert.equal(
    buildCourseDetailWorkspacePath({
      courseId: "course_123",
      topicId: "topic_abc",
      returnTo: "/courses/detail/course_123",
    }),
    "/study/course_123?topic=topic_abc&returnTo=%2Fcourses%2Fdetail%2Fcourse_123"
  );
});

test("buildCourseDetailWorkspacePath preserves the course detail return path for task deep links", () => {
  assert.equal(
    buildCourseDetailWorkspacePath({
      courseId: "course_123",
      taskId: "task_1",
      returnTo: "/courses/detail/course_123",
    }),
    "/study/course_123?task=task_1&returnTo=%2Fcourses%2Fdetail%2Fcourse_123"
  );
});

test("buildCourseDetailWorkspacePath supports entering workspace without a specific task or topic", () => {
  assert.equal(
    buildCourseDetailWorkspacePath({
      courseId: "course_123",
      returnTo: "/courses/detail/course_123",
    }),
    "/study/course_123?returnTo=%2Fcourses%2Fdetail%2Fcourse_123"
  );
});
