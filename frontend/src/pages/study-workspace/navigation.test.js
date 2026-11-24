import test from "node:test";
import assert from "node:assert/strict";

import { buildLegacySetupRedirectPath, buildWorkspaceBackPath } from "./navigation.js";

test("redirects legacy created flow from workspace to course detail", () => {
  assert.equal(
    buildLegacySetupRedirectPath("/study/course_123", "?created=1&processing=1&sourceCount=2"),
    "/courses/detail/course_123?created=1&processing=1&sourceCount=2"
  );
});

test("keeps explicit task deep links in workspace", () => {
  assert.equal(
    buildLegacySetupRedirectPath("/study/course_123", "?created=1&task=task_1"),
    ""
  );
});

test("ignores non-created workspace routes", () => {
  assert.equal(
    buildLegacySetupRedirectPath("/study/course_123", "?topic=topic_1"),
    ""
  );
});

test("buildWorkspaceBackPath prefers the explicit return path from course detail", () => {
  assert.equal(
    buildWorkspaceBackPath("/study/course_123", "?returnTo=%2Fcourses%2Fdetail%2Fcourse_123"),
    "/courses/detail/course_123"
  );
});

test("buildWorkspaceBackPath falls back to the current course detail page", () => {
  assert.equal(
    buildWorkspaceBackPath("/study/course_123", "?topic=topic_1"),
    "/courses/detail/course_123"
  );
});

test("buildWorkspaceBackPath ignores external or protocol-relative return paths", () => {
  assert.equal(
    buildWorkspaceBackPath("/study/course_123", "?returnTo=https%3A%2F%2Fevil.example"),
    "/courses/detail/course_123"
  );
  assert.equal(
    buildWorkspaceBackPath("/study/course_123", "?returnTo=%2F%2Fevil.example"),
    "/courses/detail/course_123"
  );
});
