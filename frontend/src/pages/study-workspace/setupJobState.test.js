import test from "node:test";
import assert from "node:assert/strict";

import { buildCourseSetupFailureState } from "./setupJobState.js";

test("buildCourseSetupFailureState prefers backend syllabus detail for UI", () => {
  const state = buildCourseSetupFailureState(
    {
      detail: "LLM syllabus extraction failed after 2 attempts: timeout",
      syllabus: { status: "failed", percent: 100, message: "Thất bại" },
      practice: { status: "failed", percent: 0, message: "Thất bại" },
      schedule: { status: "failed", percent: 0, message: "Thất bại" },
    },
    { syllabus: { parsedJson: { error: "older message" } } },
    []
  );

  assert.equal(state.status, "error");
  assert.equal(state.error, "LLM syllabus extraction failed after 2 attempts: timeout");
  assert.equal(state.syllabus.status, "failed");
  assert.equal(state.schedule.status, "failed");
  assert.equal(state.practice.status, "failed");
});
